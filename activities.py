import io
import json
import os
import base64
from docx import Document
import PyPDF2

from temporalio import activity
from openai import OpenAI

from dotenv import load_dotenv




load_dotenv()

client = OpenAI(
    base_url=os.getenv("QWEN_BASE_URL"),
    api_key=os.getenv("QWEN_API_KEY"),
)

model = os.getenv("QWEN_MODEL_NAME")

@activity.defn
async def parse_file_activity(file_content:bytes, file_name:str) -> str:
    file_type = file_name.split('.')[-1].lower()
    
    if file_type == 'docx':
        doc = Document(io.BytesIO(file_content))
        text = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
        return text
    
    elif file_type == 'pdf':
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ''
        for page in pdf_reader.pages:
            text += page.extract_text() + '\n'
        return text.strip()
    
    elif file_type == 'txt':
        return file_content.decode('utf-8')
    
    return 'Неподдерживаемый формат'

@activity.defn
async def ocr_document_activity(file_bytes: bytes) -> str:
    """
    если обычное чтение не справилось, включается ocr
    """
    base64_image = base64.b64encode(file_bytes).decode('utf-8')
    
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Прочитай весь текст с этого изображения."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
        ],
    }]

    response = ai_client.chat.completions.create(
        model=MODEL_NAME, messages=messages, max_tokens=2048
    )
    return response.choices[0].message.content

@activity.defn
async def save_budget_stub(data: dict) -> str:
    #Заглушка пока нет базы данных и алгоритма расчета
    print(f'якобы сохранение в постгрес {data}')
    return "ok"


@activity.defn
async def analyze_tz_activity(text: str) -> dict:
    """Анализ ТЗ и извлечение JSON"""
    prompt = f"""
    Проанализируй текст ТЗ и извлеки ключевую информацию в формате JSON.
    Поля: client_name, project_type, deadline, key_features (list), tech_stack.
    Верни ТОЛЬКО JSON.
    
    Текст: {text[:10000]}
    """
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты системный аналитик. Отвечай только валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        raw_content = response.choices[0].message.content
        # Очистка от Markdown
        clean_content = raw_content.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_content)
    except Exception as e:
        activity.logger.error(f"LLM Error: {e}")
        # Возвращаем структуру с ошибкой, чтобы workflow не падал
        return {"client_name": "Ошибка анализа", "key_features": []}

@activity.defn
async def generate_proposal_activity(requirements: dict, price: float) -> str:
    """Генерация текста КП"""
    #дописать как нам надо
    prompt = f"""
    Напиши коммерческое предложение.
    Клиент: {requirements.get('client_name')}
    Бюджет: {price}
    Фичи: {requirements.get('key_features')}
    """
    
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content




@activity.defn
async def analyze_requirements_activity(text: str) -> dict:
    """
    Анализ текста через vLLM. Извлечение JSON.
    """
    prompt = f"""
    Извлеки данные из ТЗ в формате JSON: client_name, deadline, key_features.
    Текст: {text[:10000]} 
    """ # Обрезаем текст, если слишком длинный
    
    response = ai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    
    # Тут твоя логика очистки JSON (strip, replace...)
    raw_json = response.choices[0].message.content
    # ... parsing logic ...
    return json.loads(raw_json) # Заглушка, в реальности нужен try/except
