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

# client = OpenAI(...)  <-- Removed global init


MODEL_NAME = os.getenv("QWEN_MODEL_NAME")

@activity.defn
async def parse_file_activity(file_content:bytes, file_name:str) -> str:
    file_type = file_name.split('.')[-1].lower()
    
    # --- Docling Integration ---
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice

    # Настройка Docling для использования GPU (если доступно)
    # Важно: это должно выполняться внутри activity или при старте worker'а.
    # Для эффективности можно создать глобальный converter, но с осторожностью в мультипроцессинге.
    # Temporal activities запускаются в asyncio loop, Docling синхронный/асинхронный.

    try:
        # Настройка пайплайна для PDF
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        
        # Настройка ускорителя (GPU)
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=4, device=AcceleratorDevice.CUDA
        )

        doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    except Exception as e:
        print(f"Ошибка инициализации Docling: {e}. Используем fallback.")
        doc_converter = DocumentConverter() # Fallback config

    # Сохраняем во временный файл, так как Docling работает с путями или потоками
    # Для простоты используем BytesIO, если Docling поддерживает, или tempfile
    
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp_file:
        tmp_file.write(file_content)
        tmp_path = Path(tmp_file.name)

    try:
        # Конвертация
        print(f"Начинаю парсинг файла {file_name} с помощью Docling...")
        result = doc_converter.convert(tmp_path)
        
        # Получение Markdown
        markdown_text = result.document.export_to_markdown()
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
        return markdown_text

    except Exception as e:
        print(f"Ошибка Docling: {e}")
        if os.path.exists(tmp_path):
             os.unlink(tmp_path)
        return f"Ошибка при обработке файла: {e}"

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

    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )
    response = client.chat.completions.create(
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
    1. "client_name": Название компании.
    2. "business_goals": Список ключевых задач бизнеса (какие проблемы решает продукт, зачем он нужен).
    3. "project_essence": Краткая суть проекта в 1-2 предложениях (Summary).
    4. "key_features": Список функциональных требований.
    5. "tech_stack": Рекомендуемый стек (если указан в ТЗ). Если не указан - напиши "Не указан в ТЗ". НЕ ПРИДУМЫВАЙ.
    6. "project_type": Тип проекта (Web, Mobile, ML, Design).

    Верни ТОЛЬКО JSON.
    
    Текст: {text[:10000]}
    """
    
    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )
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
async def generate_proposal_activity(data: dict, budget_matrix: dict, rates: dict) -> str:
    """Генерация текста КП"""

    # Формируем текстовое описание сметы для ИИ из матрицы
    detailed_budget_text = "Детальный расчет трудозатрат по этапам:\n"
    total_project_sum = 0
    
    for stage, roles_hours in budget_matrix.items():
        detailed_budget_text += f"Этап '{stage}':\n"
        for role, hours in roles_hours.items():
            if hours > 0:
                rate = rates.get(role, 0)
                cost = hours * rate
                total_project_sum += cost
                detailed_budget_text += f"  - {role}: {hours} ч. по {rate} р./час = {cost} р.\n"

    prompt = f"""
    Напиши профессиональное коммерческое предложение.

    ДАННЫЕ ДЛЯ ВКЛЮЧЕНИЯ В ДОКУМЕНТ:
    1. Суть проекта: {data.get('project_essence')}
    2. Бизнес-задачи: {data.get('business_goals')}
    3. Ключевой функционал: {data.get('key_features')}
    4. Этапы и Стек: {data.get('tech_stack')}
    
    ФИНАНСОВЫЙ РАЗДЕЛ (Оформи красиво в Markdown таблице):
    {detailed_budget_text}
    ИТОГО СТОИМОСТЬ: {total_project_sum} руб.

    Стиль: Убедительный, деловой.
    """
    
    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )
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
    
    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    
    # Тут твоя логика очистки JSON (strip, replace...)
    raw_json = response.choices[0].message.content
    # ... parsing logic ...
    return json.loads(raw_json) # Заглушка, в реальности нужен try/except
