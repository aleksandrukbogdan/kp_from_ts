
import io
import json
import os
import base64
import re
import threading
import asyncio
from pathlib import Path
from temporalio import activity
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv

# New Modules
from llm_service import LLMService
from schemas import (
    ExtractedTZData, 
    AnalysisTZResult, 
    BudgetResult, 
    ProposalResult, 
    KeyFeaturesDetails,
    SourceText
)
from utils_text import split_markdown, merge_extracted_data

load_dotenv()

MODEL_NAME = os.getenv("QWEN_MODEL_NAME")

# --- Global Shared Resources ---
_doc_converter = None
_doc_converter_lock = threading.Lock()

def get_docling_converter():
    """Thread-safe singleton for Docling converter."""
    global _doc_converter
    with _doc_converter_lock:
        if _doc_converter is not None:
            return _doc_converter

        # --- Docling Integration ---
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice

        is_dev = os.getenv("IS_DEV", "false").lower() == "true"
        
        try:
            # Pipeline Setup
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True
            
            # Accelerator Setup
            device = AcceleratorDevice.CPU if is_dev else AcceleratorDevice.CUDA
            print(f"Docling initialising... IS_DEV={is_dev}, Device={device}")
            
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=4, device=device
            )

            _doc_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        except Exception as e:
            print(f"Docling Init Error: {e}. using fallback.")
            _doc_converter = DocumentConverter() # Fallback
        
        return _doc_converter

@activity.defn
async def parse_file_activity(file_path:str, file_name:str) -> str:
    """Parses document via Docling and saves Markdown to a file. Returns path to MD file."""
    doc_converter = get_docling_converter()
    input_path = Path(file_path)

    try:
        activity.logger.info(f"Docling: Starting parsing for {file_path}...")
        
        # Offload CPU-bound task to a separate thread to prevent blocking Temporal heartbeat
        # We need to wrap the sync call
        def _run_docling():
            return doc_converter.convert(input_path)

        result = await asyncio.to_thread(_run_docling)
        activity.logger.info("Docling: Conversion successful.")
        
        markdown_text = result.document.export_to_markdown()
        
    except Exception as e:
        activity.logger.error(f"Docling Error: {e}")
        
        # Lightweight Fallback for DOCX
        markdown_text = ""
        try:
            if str(input_path).endswith(".docx"):
                activity.logger.info("Attempting lightweight DOCX fallback...")
                import docx
                doc = docx.Document(file_path)
                markdown_text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as fallback_e:
            activity.logger.error(f"Fallback Error: {fallback_e}")

        if not markdown_text:
            return ""

    # Save Markdown to a separate file (Blob Pattern) to avoid bloating Temporal History
    md_filename = f"{input_path.stem}_parsed.md"
    md_path = input_path.parent / md_filename
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
        
    return str(md_path)

@activity.defn
async def ocr_document_activity(file_path: str) -> str:
    """Fallback OCR if standard parsing fails."""
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Transcribe ALL text from this image exactly as it appears. Detect layout if possible."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            ],
        }]

        llm = LLMService()
        text = await llm.create_chat_completion(messages=messages)
        
        # Save OCR result to file as well
        input_path = Path(file_path)
        md_path = input_path.parent / f"{input_path.stem}_ocr.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
            
        return str(md_path)
        
    except Exception as e:
        activity.logger.error(f"OCR Activity Error: {e}")
        return "" # Signal failure

@activity.defn
async def save_budget_stub(data: dict) -> str:
    """Stub for database saving."""
    print(f'Stub saving to Postgres: {data}')
    return "ok"

@activity.defn
async def estimate_hours_activity(tz_data: dict, stages: list, roles: list) -> dict:
    """
    Generates Budget Matrix: Stage -> Role -> Hours
    """
    llm = LLMService()
    
    try:
        activity.logger.info("Starting Budget Estimation")
        budget_result: BudgetResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": "Ты Project Manager. Оцени трудозатраты в часах для каждого этапа и роли. "
                                              "Используй ТОЛЬКО предложенные этапы и роли. Отвечай на РУССКОМ (названия могут быть англ, но суть русская)."},
                {"role": "user", "content": f"""
Проект: {tz_data.get('project_essence', 'N/A')}
Стек: {tz_data.get('tech_stack', [])}

Этапы (stages): {stages}
Роли (roles): {roles}

Заполни матрицу часов:
Для КАЖДОГО этапа из списка Stages укажи часы для КАЖДОЙ роли из списка Roles.
Если роль не участвует в этапе, ставь 0.
                """}
            ],
            output_model=BudgetResult,
            tool_name="submit_budget"
        )
        
        # Transform to Matrix format: {Stage: {Role: Hours}}
        matrix = {}
        
        # Index results
        for stage_est in budget_result.stages:
            s_name = stage_est.stage_name
            matrix[s_name] = {}
            for role_est in stage_est.role_estimates:
                matrix[s_name][role_est.role_name] = role_est.hours

        # Ensure full matrix based on requested stages/roles (fill missing with 0)
        final_matrix = {}
        for stage in stages:
            final_matrix[stage] = {}
            for role in roles:
                val = 0
                # Try exact match or loose matching if needed
                if stage in matrix and role in matrix[stage]:
                    val = matrix[stage][role]
                final_matrix[stage][role] = val
                
        return final_matrix

    except Exception as e:
        activity.logger.error(f"Budget Estimation Error: {e}")
        # Return empty matrix
        return {stage: {role: 0 for role in roles} for stage in stages}

@activity.defn
async def generate_proposal_activity(data: dict, budget_matrix: dict, rates: dict) -> str:
    """Generates Commercial Proposal Markdown"""
    llm = LLMService()
    
    # Pre-calculate budget text
    detailed_budget_text = "### Estimated Budget\n\n| Stage | Role | Hours | Rate | Cost |\n|---|---|---|---|---|\n"
    total_sum = 0
    
    for stage, roles_hours in budget_matrix.items():
        for role, hours in roles_hours.items():
            if hours > 0:
                rate = rates.get(role, 0)
                cost = hours * rate
                total_sum += cost
                detailed_budget_text += f"| {stage} | {role} | {hours} | {rate} | {cost} |\n"
    
    detailed_budget_text += f"\n**Total Estimated Cost: {total_sum} RUB**"

    try:
        proposal: ProposalResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": "Ты Менеджер по продажам. Напиши убедительное Коммерческое Предложение в формате Markdown на РУССКОМ языке."},
                {"role": "user", "content": f"""
Суть проекта: {data.get('project_essence')}
Цели: {data.get('business_goals')}
Функционал: {data.get('key_features')}
Стек: {data.get('tech_stack')}

Бюджет (включи эту таблицу в КП):
{detailed_budget_text}

Напиши полное КП со структурой: Введение, Понимание задачи, Решение (Стек, Функции), План работ, Бюджет (вставь таблицу), Призыв к действию.
                """}
            ],
            output_model=ProposalResult,
            tool_name="submit_proposal"
        )
        return proposal.markdown_content

    except Exception as e:
        activity.logger.error(f"Proposal Generation Error: {e}")
        return "Error generating proposal."

# --- New Map-Reduce Activities ---

def _split_text_sync(md_file_path: str) -> List[Dict[str, Any]]:
    """Sync implementation of splitting to be run in thread. Uses BYTES to avoid seek issues."""
    CHUNK_SIZE = 12000 # Bytes approximately
    OVERLAP = 1000     # Bytes
    
    chunks_defs = []
    
    try:
        if not os.path.exists(md_file_path):
             print(f"File not found for splitting: {md_file_path}")
             return []

        # OPEN AS BYTES
        with open(md_file_path, "rb") as f:
            content = f.read()
            
        text_len = len(content)
        start = 0
        
        if text_len == 0:
             return []

        while start < text_len:
            end = min(start + CHUNK_SIZE, text_len)
            
            # Smart split: Try to find a newline byte b'\n' to break cleanly
            if end < text_len:
                # Look for newline in the last 500 bytes of the chunk
                # Ensure we don't start search before start
                search_start = max(start, end - 500)
                search_window = content[search_start : end]
                
                last_newline = search_window.rfind(b'\n')
                if last_newline != -1:
                    # Adjust end to the newline. 
                    # last_newline is relative to search_window start.
                    end = search_start + last_newline + 1 # +1 to include \n
            
            chunks_defs.append({
                "file_path": md_file_path,
                "start": start,
                "end": end
            })
            
            # Move start for next chunk, accounting for overlap
            if end >= text_len:
                break
                
            # Overlap logic: Move back N bytes
            start = max(0, end - OVERLAP)
            
            # Align new start to a character boundary (avoid continuation bytes 0x80-0xBF)
            # UTF-8: Multi-byte chars start with 11xxxxxx (0xC0+). Continuation bytes are 10xxxxxx (0x80-0xBF).
            # ASCII is 0xxxxxxx (<0x80).
            # So if byte is >= 0x80 and < 0xC0, it's a continuation byte.
            while start < text_len and (content[start] & 0xC0 == 0x80):
                start += 1
            
        return chunks_defs
        
    except Exception as e:
        print(f"Split Text Failed: {e}")
        return []

@activity.defn
async def split_text_activity(md_file_path: str) -> List[Dict[str, Any]]:
    """
    Reads the markdown file and defines chunks.
    Returns a list of Chunk Definitions: {'file_path': str, 'start': int, 'end': int}
    """
    # Offload to thread to avoid Heartbeat timeout on large files
    return await asyncio.to_thread(_split_text_sync, md_file_path)

@activity.defn
async def extract_chunk_activity(chunk_def: Dict[str, Any]) -> dict:
    """Phase 1: Extraction for a single chunk (reading from file)."""
    llm = LLMService()
    try:
        file_path = chunk_def["file_path"]
        start = chunk_def["start"]
        end = chunk_def["end"]
        
        chunk_text = ""
        # OPEN AS BYTES
        with open(file_path, "rb") as f:
            f.seek(start)
            chunk_bytes = f.read(end - start)
            # Decode safely, ignoring errors at boundaries if overlap caused cuts
            chunk_text = chunk_bytes.decode('utf-8', errors='ignore')
            
        activity.logger.info(f"Extracting data from chunk ({len(chunk_text)} chars)...")
        
        system_prompt = """Ты вдумчивый Системный Аналитик. Твоя задача — внимательно прочитать часть ТЗ и извлечь данные.
        
Шаг 1: РАССУЖДЕНИЕ (Reasoning)
Сначала заполни поле 'reasoning'. В нем опиши своими словами:
- О чем этот текст?
- Какие ключевые функции или модули здесь описаны?
- Видишь ли ты конкретные технологии или цели?
Только после того, как ты проговоришь это, заполняй остальные поля.

Шаг 2: ИЗВЛЕЧЕНИЕ (Extraction)
Заполни остальные поля JSON.
- client_name: Ищи название компании-заказчика. Если не найдено, верни пустую строку "".
- project_type: Выбери один вариант, который ЛУЧШЕ ВСЕГО подходит: [Web, Mobile, ERP, CRM, AI, Integration, Other].
    - Если система обрабатывает документы - скорее всего ERP или AI (если есть LLM).
    - Если это мобильное приложение - Mobile.
    - Если сайт - Web.
- key_features: Разбей найденное на категории.

ВАЖНОЕ ПРАВИЛО ФОРМАТИРОВАНИЯ:
- В полях 'text' пиши ЧИСТЫЙ ТЕКСТ.
- ЗАПРЕЩЕНО писать "Unknown", "N/A", "Нет". Просто пустая строка.
"""
        
        extracted_data: ExtractedTZData = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Часть ТЗ:\n\n{chunk_text}"}
            ],
            output_model=ExtractedTZData,
            tool_name="extract_tz_chunk"
        )
        return extracted_data.model_dump()
    except Exception as e:
        activity.logger.error(f"Chunk Extraction Failed: {e}")
        # Return empty structure - soft failure, workflow continues
        return ExtractedTZData().model_dump()

@activity.defn
async def merge_data_activity(data_list: List[dict]) -> dict:
    """Aggregates list of partial results."""
    # Convert dicts back to models
    try:
        models = [ExtractedTZData(**d) for d in data_list]
        merged = merge_extracted_data(models)
        return merged.model_dump()
    except Exception as e:
        activity.logger.error(f"Merge Failed: {e}")
        return ExtractedTZData(project_essence=SourceText(text=f"Merge Error: {e}")).model_dump()

@activity.defn
async def analyze_project_activity(merged_data: dict) -> dict:
    """
    Phase 2: Analysis based on aggregated data.
    Populates requirement_issues, suggested_stages, suggested_roles, and estimates.
    """
    llm = LLMService()
    
    # We rely on the structured extracted data.
    # START OPTIMIZATION: Filter context to avoid 50k+ char payloads
    condensed_data = {
        "project_essence": merged_data.get("project_essence", ""),
        "project_type": merged_data.get("project_type", ""),
        "business_goals": merged_data.get("business_goals", ""),
        "tech_stack": merged_data.get("tech_stack", []),
        "key_features": merged_data.get("key_features", {}), 
        # Exclude 'client_integrations' if it's just raw text, or keep if crucial. 
        # 'screens', 'reports' inside key_features might be enough.
    }
    
    context_json = json.dumps(condensed_data, indent=2, ensure_ascii=False)
    # END OPTIMIZATION
    
    try:
        activity.logger.info("Starting Project Analysis (Phase 2)")
        analysis_result: AnalysisTZResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": "Ты IT Архитектор. Проанализируй данные проекта. Отвечай на РУССКОМ."},
                {"role": "user", "content": f"""
Данные проекта (извлеченные из ТЗ):
{context_json}

Задачи:
1. Найди проблемные требования (неясные, противоречивые) в extracted data.
2. Предложи этапы разработки и роли.
3. Оцени часы (от 4 до 100) на КАЖДУЮ функцию из key_features.

ВАЖНО ДЛЯ requirement_issues:
- Поле "item_text" должно содержать ТОЛЬКО текст требования (например: "Система должна работать офлайн"). 
- НЕ пиши туда JSON или Python-объекты вроде "text='...' source='...'".
- Если проблема общая, напиши суть своими словами.
                """}
            ],
            output_model=AnalysisTZResult,
            tool_name="submit_analysis_v2"
        )
    except Exception as e:
        activity.logger.error(f"Analysis Phase Failed: {e}")
        # Return merged data as is
        return merged_data

    # Map results back to the main dict
    final_dict = merged_data.copy()
    analysis_dict = analysis_result.model_dump()

    final_dict["requirement_issues"] = analysis_dict["requirement_issues"]
    final_dict["suggested_stages"] = analysis_dict["suggested_stages"]
    final_dict["suggested_roles"] = analysis_dict["suggested_roles"]

    # Map estimates
    estimates_map = {est['feature_text']: est['hours'] for est in analysis_dict.get('estimates', [])}
    key_features = final_dict.get("key_features", {})
    
    if isinstance(key_features, dict):
        for category, features in key_features.items():
            if not isinstance(features, list): continue
            for feature in features:
                f_text = feature.get("text", "")
                hours = 5
                
                # Check match
                # Try exact
                if f_text in estimates_map:
                    hours = estimates_map[f_text]
                else:
                    # Try fuzzy
                    for est_text, h in estimates_map.items():
                        if est_text in f_text or f_text in est_text:
                            hours = h
                            break
                
                feature["estimated_hours"] = hours
                feature["category"] = category

    return final_dict
