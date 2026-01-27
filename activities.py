import io
import json
import os
import base64

from temporalio import activity
from openai import OpenAI

from dotenv import load_dotenv




load_dotenv()

# client = OpenAI(...)  <-- Removed global init


MODEL_NAME = os.getenv("QWEN_MODEL_NAME")

# Глобальная переменная для кэширования конвертера
_doc_converter = None

def get_docling_converter():
    global _doc_converter
    if _doc_converter is not None:
        return _doc_converter

    # --- Docling Integration ---
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice

    is_dev = os.getenv("IS_DEV", "false").lower() == "true"
    
    try:
        # Настройка пайплайна для PDF
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        
        # Настройка ускорителя
        # Если IS_DEV=true (локально), используем CPU. Иначе - CUDA.
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
        print(f"Ошибка инициализации Docling: {e}. Используем fallback.")
        _doc_converter = DocumentConverter() # Fallback config
    
    return _doc_converter

@activity.defn
async def parse_file_activity(file_content:bytes, file_name:str) -> str:
    """Парсинг документа через Docling. Возвращает Markdown."""
    file_type = file_name.split('.')[-1].lower()
    
    # Получаем инициализированный конвертер
    doc_converter = get_docling_converter()

    # Сохраняем во временный файл, так как Docling работает с путями или потоками
    # Для простоты используем BytesIO, если Docling поддерживает, или tempfile
    
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp_file:
        tmp_file.write(file_content)
        tmp_path = Path(tmp_file.name)

    try:
        # Конвертация
        print(f"Docling: Начинаю парсинг файла {file_name} (размер: {len(file_content)} байт)...")
        # is_dev доступен через os.getenv, но для логов можно повторить или пропустить, 
        # так как это уже выводится при инициализации
            
        result = doc_converter.convert(tmp_path)
        print("Docling: Конвертация завершена успешно.")
        
        # Получение Markdown
        markdown_text = result.document.export_to_markdown()
        
        # Удаляем временный файл
        if os.path.exists(tmp_path):
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
    """Анализ ТЗ и извлечение JSON с детальными цитатами для каждого пункта"""
    # Ограничение контекста для модели (настраивается через TZ_MAX_CHARS)
    MAX_CHARS = int(os.getenv("TZ_MAX_CHARS", "90000"))
    truncated_text = text[:MAX_CHARS]
    if len(text) > MAX_CHARS:
        print(f"Warning: Текст обрезан с {len(text)} до {MAX_CHARS} символов для LLM.")
    
    prompt = f"""
Извлеки данные из технического задания в формате JSON:

1. "client_name": Название компании.

2. "business_goals": Массив объектов. Каждый объект:
   {{"text": "формулировка цели", "source": "точная цитата из ТЗ, откуда это взято"}}

3. "project_essence": Краткая суть проекта в 1-2 предложениях.
   
4. "key_features": Массив объектов. Каждый объект:
   {{"text": "название функции/требования", "source": "точная цитата из ТЗ"}}

5. "tech_stack": Массив объектов (если указан в ТЗ). Каждый объект:
   {{"text": "технология", "source": "цитата из ТЗ"}}
   Если не указан — пустой массив [].

6. "client_integrations": Массив объектов. Каждый объект:
   {{"text": "название интеграции", "source": "цитата из ТЗ"}}
   Если нет — пустой массив [].

7. "project_type": Тип проекта (Web, Mobile, ML, Design).

8. "requirement_issues": Массив проблемных требований. Каждый объект:
   - "type": один из ["questionable", "impossible", "contradictory"]
   - "field": к какому полю относится ("key_features", "business_goals", "client_integrations" и т.д.)
   - "item_text": текст проблемного пункта (должен совпадать с text в соответствующем поле)
   - "source": цитата из ТЗ
   - "reason": причина, почему это проблема
   
   Типы:
   - "questionable" — нечёткие требования без конкретики
   - "impossible" — технически нереализуемые требования  
   - "contradictory" — требования, противоречащие другим пунктам ТЗ
   
   Если проблем нет — пустой массив [].

9. "source_excerpts": Объект с общими цитатами для полей, которые не являются массивами:
   - "client_name": цитата, откуда взято название компании
   - "project_essence": цитата с описанием сути проекта

10. "suggested_stages": Массив рекомендуемых этапов работ для этого проекта.
    Например: ["Аналитика", "Дизайн", "Разработка MVP", "Тестирование", "Запуск"]

11. "suggested_roles": Массив рекомендуемых ролей для команды.
    Например: ["Менеджер", "Дизайнер", "Frontend", "Backend", "ML-инженер", "QA"]

ВАЖНО: Каждая цитата в "source" должна быть ТОЧНЫМ фрагментом текста из ТЗ (до 300 символов).

Верни ТОЛЬКО валидный JSON.

Текст ТЗ:
{truncated_text}
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
        result = json.loads(clean_content)
        
        # Гарантируем наличие полей
        if "requirement_issues" not in result:
            result["requirement_issues"] = []
        if "source_excerpts" not in result:
            result["source_excerpts"] = {}
        if "suggested_stages" not in result:
            result["suggested_stages"] = ["Сбор данных", "Прототип", "Разработка", "Тестирование"]
        if "suggested_roles" not in result:
            result["suggested_roles"] = ["Менеджер", "Frontend", "Backend", "Дизайнер"]
            
        return result
    except Exception as e:
        activity.logger.error(f"LLM Error: {e}")
        # Возвращаем структуру с ошибкой, чтобы workflow не падал
        return {
            "client_name": "Ошибка анализа", 
            "key_features": [],
            "requirement_issues": [],
            "source_excerpts": {},
            "suggested_stages": ["Сбор данных", "Прототип", "Разработка", "Тестирование"],
            "suggested_roles": ["Менеджер", "Frontend", "Backend", "Дизайнер"]
        }

@activity.defn
async def estimate_hours_activity(tz_data: dict, stages: list, roles: list) -> dict:
    """
    Оценка трудозатрат на основе ТЗ, этапов и ролей.
    Возвращает матрицу: {"Этап": {"Роль": часы}}
    """
    prompt = f"""
На основе данных из технического задания, оцени трудозатраты в часах.

Данные проекта:
- Суть проекта: {tz_data.get('project_essence', 'Не указано')}
- Тип проекта: {tz_data.get('project_type', 'Не указан')}
- Ключевой функционал: {tz_data.get('key_features', [])}
- Стек: {tz_data.get('tech_stack', 'Не указан')}
- Интеграции: {tz_data.get('client_integrations', [])}

Этапы работ: {stages}
Роли в команде: {roles}

Верни JSON-объект, где ключи — названия этапов, значения — объекты с ролями и часами.
Пример:
{{
  "Сбор данных": {{"Менеджер": 8, "ML-Инженер": 4, "Frontend": 0, "Backend": 2, "Дизайнер": 0}},
  "Прототип": {{"Менеджер": 4, "ML-Инженер": 0, "Frontend": 8, "Backend": 0, "Дизайнер": 16}}
}}

Оценивай реалистично для типичного проекта. Если роль не нужна на этапе — ставь 0.
Верни ТОЛЬКО валидный JSON.
    """
    
    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты опытный project-менеджер. Отвечай только валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        raw_content = response.choices[0].message.content
        clean_content = raw_content.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_content)
    except Exception as e:
        activity.logger.error(f"Estimate Hours Error: {e}")
        # Возвращаем пустую матрицу при ошибке
        return {stage: {role: 0 for role in roles} for stage in stages}

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
    5. Требуемые интеграции: {data.get('client_integrations')}
    
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
    MAX_CHARS = int(os.getenv("TZ_MAX_CHARS", "90000"))
    prompt = f"""
    Извлеки данные из ТЗ в формате JSON: client_name, deadline, key_features.
    Tекст: {text[:MAX_CHARS]} 
    """
    
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
