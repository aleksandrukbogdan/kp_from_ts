import os
import json
import logging
import asyncio
import re
from typing import Type, TypeVar, List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APITimeoutError, APIError
from pydantic import BaseModel, ValidationError

load_dotenv()

# Setup Structured Logging
logger = logging.getLogger("llm_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "service": "llm_service", "message": "%(message)s"}')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

T = TypeVar("T", bound=BaseModel)

class LLMProcessingError(Exception):
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)

class LLMService:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMService, cls).__new__(cls)
            cls._instance._initialize_client()
        return cls._instance

    def _initialize_client(self):
        """Initializes the OpenAI client using environment variables."""
        base_url = os.getenv("QWEN_BASE_URL")
        api_key = os.getenv("QWEN_API_KEY")
        self.model_name = os.getenv("QWEN_MODEL_NAME", "qwen-2.5-32b-instruct")

        if not base_url or not api_key:
            logger.warning("Missing QWEN_BASE_URL or QWEN_API_KEY. LLM calls will fail.")
        
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            max_retries=0 # We handle retries manually
        )
        logger.info(f"LLMService initialized with model: {self.model_name}")

    def _clean_json_string(self, content: str) -> str:
        """Cleans Markdown code blocks and common formatting issues from JSON string."""
        content = content.strip()
        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        return content.strip()

    async def create_structured_completion(
        self, 
        messages: List[Dict[str, Any]], 
        output_model: Type[T],
        tool_name: str,
        temperature: float = 0.1,
        max_retries: int = 3,
        timeout: int = 1200
    ) -> T:
        """
        Executes an LLM call using JSON Mode.
        Validates result against the provided Pydantic model.
        Handles retries for transient errors.
        Raises LLMProcessingError for specific failures.
        """
        # Prepare Schema for Prompting
        schema_json = json.dumps(output_model.model_json_schema(), ensure_ascii=False, indent=2)
        
        # Inject Schema
        current_messages = [m.copy() for m in messages]
        schema_instruction = (
            f"\n\nIMPORTANT: Output MUST be a valid JSON object strictly matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            "Do NOT output markdown blocks (like ```json ... ```) nicely, just raw JSON is preferred but markdown is acceptable if valid.\n"
            "Do NOT write any explanations."
        )

        if current_messages and current_messages[0]['role'] == 'system':
            current_messages[0]['content'] += schema_instruction
        else:
            current_messages.insert(0, {"role": "system", "content": schema_instruction})

        last_exception = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Requesting '{tool_name}' [Attempt {attempt+1}/{max_retries}] (JSON Mode)")
                
                # Debug: Log input messages (truncated)
                debug_msgs = json.dumps(current_messages, ensure_ascii=False, default=str)
                logger.debug(f"LLM Input Messages len: {len(debug_msgs)}")

                start_time = asyncio.get_event_loop().time()
                
                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=self.model_name,
                    messages=current_messages,
                    # Removing tools/tool_choice to avoid "tools param requires --jinja flag" error
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=8192, # Increased for larger JSONs
                    timeout=timeout
                )
                
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"LLM Response received in {elapsed:.2f}s")

                raw_content = response.choices[0].message.content
                if not raw_content:
                    logger.warning("Empty response from LLM.")
                    raise ValueError("LLM returned empty response")

                # Robust parsing
                cleaned_json = self._clean_json_string(raw_content)
                
                try:
                    data = json.loads(cleaned_json)
                except json.JSONDecodeError:
                    # Attempt simple fix
                    try:
                        data = json.loads(cleaned_json, strict=False)
                    except json.JSONDecodeError:
                         # Last resort: regex
                        match = re.search(r'\{.*\}', cleaned_json, re.DOTALL)
                        if match:
                             data = json.loads(match.group(0))
                        else:
                             raise

                # Pydantic Validation
                validated_obj = output_model.model_validate(data)
                return validated_obj

            except (RateLimitError, APITimeoutError) as e:
                logger.warning(f"Transient LLM Error: {e}. Retrying in {2**attempt}s...")
                await asyncio.sleep(2**attempt)
                last_exception = e
                
            except APIError as e:
                # 400 Bad Request usually means Context Window Exceeded
                if e.code == 'context_length_exceeded' or (e.message and 'context' in e.message.lower()):
                     logger.error("Context Window Limit Exceeded.")
                     raise LLMProcessingError("Document too large for model context.", "CONTEXT_LIMIT")
                
                # 500 or others could be OOM on server side
                logger.error(f"API Error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                last_exception = e

            except (ValidationError, json.JSONDecodeError) as e:
                logger.error(f"Validation/Parsing Error: {e}.")
                
                # Self-correction: Feed error back to the model
                # NOTE: Do NOT append the full response to avoid exponential context growth
                if attempt < max_retries - 1:
                    logger.info("Feeding error back to model for self-correction...")
                    error_feedback = str(e)[:500]
                    # Instead of appending response + error, just add a simple retry prompt
                    current_messages.append({
                        "role": "user",
                        "content": f"Предыдущий ответ содержал ошибку JSON: {error_feedback}\n\nПопробуй снова. Верни ТОЛЬКО валидный JSON без markdown-разметки."
                    })
                    await asyncio.sleep(1)
                last_exception = e

            except Exception as e:
                logger.error(f"Unexpected LLM Error: {e}")
                last_exception = e
                if attempt < max_retries - 1:
                     await asyncio.sleep(1)

        # After retries exhausted, check if we have a specific error to raise
        if isinstance(last_exception, LLMProcessingError):
            raise last_exception
            
        error_msg = str(last_exception)
        if "context" in error_msg.lower():
             raise LLMProcessingError("Context Window Exceeded", "CONTEXT_LIMIT")
        
        raise LLMProcessingError(f"Processing Failed: {error_msg}", "UNKNOWN_ERROR")

    async def create_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_retries: int = 3
    ) -> str:
        """
        Standard chat completion with plain text response.
        """
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    timeout=60
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"Chat Completion Error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise e
