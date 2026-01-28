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
    """Анализ ТЗ: Двухэтапный подход для стабильности (Extraction -> Analysis)"""
    MAX_CHARS = int(os.getenv("TZ_MAX_CHARS", "180000"))
    truncated_text = text[:MAX_CHARS]
    
    client = OpenAI(
        base_url=os.getenv("QWEN_BASE_URL"),
        api_key=os.getenv("QWEN_API_KEY"),
    )

    # --- ЭТАП 1: ИЗВЛЕЧЕНИЕ ФАКТОВ (EXTRACTION PHASE) ---
    # Задача: Просто найти и процитировать, ничего не придумывать.
    # Мы просим модель вернуть JSON с цитатами.
    prompt_extract = f"""
ВАЖНО: Все ответы ДОЛЖНЫ быть на РУССКОМ языке. Не используй английский.

Проанализируй текст технического задания и извлеки фактические данные в формат JSON.
Ты можешь систематизировать информацию, но НЕ придумывай ничего, используй только то, что есть в тексте.

1. "client_name": Название компании клиента.

2. "project_essence": Суть проекта в 1-2 предложениях.

3. "project_type": Тип проекта (Web, Mobile, ML, Design, Other).

4. "business_goals": Массив целей ( [{{"text": "...", "source": "..."}}] ).

5. "tech_stack": Технологии, НА КОТОРЫХ будет написан продукт.
   Формат: [{{"text": "...", "source": "..."}}]
   ВКЛЮЧАЙ: Python, React, Vue, PostgreSQL, Docker, FastAPI, Node.js, Redis, Kubernetes
   НЕ ВКЛЮЧАЙ: 1C, SAP, Bitrix24, CRM клиента, внешние API, сторонние сервисы
   ВАЖНО: Исключи словари, глоссарии и определения терминов.

6. "client_integrations": Внешние системы, С КОТОРЫМИ продукт будет интегрироваться.
   Формат: [{{"text": "...", "source": "..."}}]
   ВКЛЮЧАЙ: 1C, SAP, Bitrix24, API банка, Telegram-бот, СДЭК, почтовые сервисы, платежные системы
   НЕ ВКЛЮЧАЙ: React, PostgreSQL, Docker (это стек разработки, а не интеграции)

7. "key_features": Объект с категориями функциональных требований.
   ВАЖНО: Извлеки ВСЕ требования из текста. Лучше включить лишнее, чем пропустить важное.
   ВАЖНО: Перечитай текст дважды — проверь таблицы, списки, приложения.
   Целевое количество: 15-50 пунктов суммарно по всем категориям.
   
   Формат:
   {{
     "modules": [{{"text": "...", "source": "..."}}],       // Логические модули системы
     "screens": [{{"text": "...", "source": "..."}}],       // UI-экраны, формы, дашборды
     "reports": [{{"text": "...", "source": "..."}}],       // Отчёты и аналитика
     "integrations": [{{"text": "...", "source": "..."}}],  // Интеграционные функции
     "nfr": [{{"text": "...", "source": "..."}}]            // Нефункциональные: производительность, безопасность, доступность
   }}

8. "source_excerpts": Объект с общими цитатами:
   - "client_name": цитата, откуда взято название
   - "project_essence": цитата с описанием сути

Каждая цитата ("source") должна быть точным фрагментом из текста.
Верни ТОЛЬКО валидный JSON.

Текст ТЗ:
{truncated_text}
    """

    try:
        response_1 = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты системный аналитик. Твоя задача — точно извлечь данные из текста. Отвечай только JSON."},
                {"role": "user", "content": prompt_extract}
            ],
            temperature=0.1
        )
        raw_json_1 = response_1.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        extracted_data = json.loads(raw_json_1)
    except Exception as e:
        activity.logger.error(f"Extraction Phase Error: {e}")
        return _get_error_stub(str(e))

    # --- ЭТАП 2: АНАЛИЗ И ОЦЕНКА (ANALYSIS PHASE) ---
    # Задача: На основе извлеченных данных сделать выводы и найти проблемы в ИСХОДНОМ ТЕКСТЕ.
    
    context_for_analysis = json.dumps(extracted_data, ensure_ascii=False, indent=2)

    prompt_analyze = f"""
Выполни аналитику проекта. Используй извлеченные данные и оригинальный текст ТЗ.

Данные проекта (из JSON):
{context_for_analysis}

Оригинальный текст ТЗ (для поиска проблем и точных цитат):
{truncated_text}

Задачи:
1. "requirement_issues": Найди проблемы в требованиях (нечеткие, противоречивые, нереализуемые).
   Формат: [{{"type": "questionable", "field": "...", "category": "...", "item_text": "...", "source": "...", "reason": "..."}}]
   Поле "field" = "key_features", поле "category" = категория (modules, screens, reports, integrations, nfr).
   ВАЖНО: Поле "source" должно быть точной цитатой из Текста ТЗ.
   ВАЖНО: Поле "reason" должно быть НА РУССКОМ ЯЗЫКЕ.
   Если проблем нет — пустой массив [].

2. "suggested_stages": Предложи этапы разработки (массив строк).
   Выбирай ТОЛЬКО из: ["Аналитика и ТЗ", "Дизайн UI/UX", "Прототипирование", "Backend", "Frontend", "Mobile", "ML/AI", "Тестирование", "Деплой", "Поддержка"].

3. "suggested_roles": Предложи команду (массив строк).
   Выбирай ТОЛЬКО из: ["PM", "Аналитик", "Дизайнер", "Frontend-dev", "Backend-dev", "Mobile-dev", "ML-Engineer", "DevOps", "QA"].

4. "key_features_estimates": Оцени каждый пункт из всех категорий "key_features" в часах (4-40 часов на фичу).
   Формат: Объект, где ключ — текст требования, значение — часы (int).
   Пройди по ВСЕМ категориям: modules, screens, reports, integrations, nfr.

Верни JSON с полями: requirement_issues, suggested_stages, suggested_roles, key_features_estimates.
    """

    try:
        response_2 = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты опытный IT-архитектор. Верни валидный JSON."},
                {"role": "user", "content": prompt_analyze}
            ],
            temperature=0.3
        )
        raw_json_2 = response_2.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        analysis_data = json.loads(raw_json_2)
        
        # --- СЛИЯНИЕ ---
        final_result = extracted_data.copy()
        final_result.update(analysis_data)
        
        # Переносим часы из key_features_estimates в key_features (теперь с категориями)
        estimates = analysis_data.get("key_features_estimates", {})
        key_features_raw = final_result.get("key_features", {})
        
        # Обработка новой структуры с категориями
        if isinstance(key_features_raw, dict):
            updated_features = {}
            for category, features_list in key_features_raw.items():
                updated_category = []
                if isinstance(features_list, list):
                    for feature in features_list:
                        if isinstance(feature, str):
                            feat_text = feature
                            feature_obj = {"text": feat_text, "source": ""}
                        else:
                            feat_text = feature.get("text", "")
                            feature_obj = feature.copy()
                        
                        hours = estimates.get(feat_text, 0)
                        # Fuzzy match fallback
                        if hours == 0:
                            for est_key, h in estimates.items():
                                if est_key in feat_text or feat_text in est_key:
                                    hours = h
                                    break
                        
                        feature_obj["estimated_hours"] = hours if hours > 0 else 5
                        feature_obj["category"] = category
                        updated_category.append(feature_obj)
                updated_features[category] = updated_category
            final_result["key_features"] = updated_features
        else:
            # Fallback для старой структуры (массив)
            updated_features = []
            features_list = key_features_raw if isinstance(key_features_raw, list) else []
            for feature in features_list:
                if isinstance(feature, str):
                    feat_text = feature
                    feature_obj = {"text": feat_text, "source": ""}
                else:
                    feat_text = feature.get("text", "")
                    feature_obj = feature.copy()
                
                hours = estimates.get(feat_text, 0)
                if hours == 0:
                    for est_key, h in estimates.items():
                        if est_key in feat_text or feat_text in est_key:
                            hours = h
                            break
                
                feature_obj["estimated_hours"] = hours if hours > 0 else 5
                updated_features.append(feature_obj)
            final_result["key_features"] = updated_features
        
        # Заглушки
        if "source_excerpts" not in final_result:
             final_result["source_excerpts"] = {}

        return final_result

    except Exception as e:
        activity.logger.error(f"Analysis Phase Error: {e}")
        extracted_data["error_analysis"] = str(e)
        extracted_data["suggested_stages"] = ["Аналитика", "Разработка"]
        extracted_data["suggested_roles"] = ["PM", "Разработчик"]
        return extracted_data

def _get_error_stub(msg: str) -> dict:
    return {
        "client_name": "Ошибка анализа",
        "project_essence": f"Не удалось обработать ТЗ: {msg}",
        "key_features": [],
        "requirement_issues": [],
        "suggested_stages": ["Аналитика"],
        "suggested_roles": ["PM"]
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
    MAX_CHARS = int(os.getenv("TZ_MAX_CHARS", "180000"))
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
