import json
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()




client = OpenAI(
    base_url=os.getenv("QWEN_BASE_URL"),
    api_key=os.getenv("QWEN_API_KEY"),
)

model = os.getenv("QWEN_MODEL_NAME")

#def _clean_env_value(value: str) -> str:
#    """Убирает лишние кавычки из значения переменной окружения."""
#    if value.startswith('"') and value.endswith('"'):
#        value = value[1:-1]
#    if value.startswith("'") and value.endswith("'"):
#        value = value[1:-1]
#    return value.strip()

def extract_requirements_from_ts(ts_text):
    """Этап 1: агент прочитал тз и вернул json"""

    promt = f"""
    
    Проанализируй текст Технического задания (ТЗ) ниже и извлеки ключевую информацию.
    Верни ответ СТРОГО в формате JSON без лишнего текста.

    Формат ответа:
{{
    "client_name": "Название компании заказчика",
    "project_type": "Тип проекта (веб, мобайл, мл и т.д.)",
    "deadline": "Срок проекта (ориентировочный)",
    "key_features": [
        "Ключевая особенность 1",
        "Ключевая особенность 2",
        "Ключевая особенность 3"
    ],
    "tech_stack": "Стек технологий (предполагаемый)"
}}

    Текст ТЗ:
    {ts_text}
    """
    try:
        response = client.chat.completions.create(

            messages=[
                {"role":"system", "content": "Ты профессиональный системный аналитик и архитектор ПО."},
                {"role":"user", "content": promt}
            ],
            model=model,
            temperature=0.2,
            
        )
        raw_content = response.choices[0].message.content
        print(raw_content)

        clean_content = raw_content.strip().replace("```json","").replace("```","")
        print(clean_content)

        return json.loads(clean_content)
    except Exception as e:
        print(f"Ошибка при обработке LLM: {str(e)}")
        return {
            "client_name": "Не удалось определить",
            "project_type": "Не удалось определить",
            "deadline": "Не удалось определить",
            "key_features": [
                "Ошибка анализа"
            ],
            "tech_stack": "Не удалось определить"
        }
    
    #заглушка на время
    #return {
    #    "client_name": "УГМК",
    #    "project_type": " Веб-платформа",
    #    "deadline": "10.03.2026",
    #    "key_features": [
    #        "Личный кабинет",
    #        "Интеграция с ЦУР",
    #        "Чат-бот поддержки"
    #    ],
    #    "tech_stack": "Python, React"
    #}
def generate_proposal(requirements, price_estimate):
    """Этап 2: генерация красивого текста предложения"""
    prompt = f"""
    Напиши профессиональное коммерческое предложени на основе следующих данных:
    Заказчик: {requirements['client_name']}
    Тип проекта: {requirements['project_type']}
    Срок проекта: {requirements['deadline']}
    Функционал: {','.join(requirements['key_features'])}
    Технологии: {requirements['tech_stack']}
    Бюджет: {price_estimate} руб.
    
    Стиль письма деловой, убедительный. Используй Markdown для оформления.
    """

    try:
        response = client.chat.completions.create(

            messages=[
                {"role":"system", "content": "Ты эксперт по продажам в IT компании."},
                {"role":"user", "content": prompt}
            ],
            model=model
        )

        return response.choices[0].message.content
    except Exception as e:
        
        return f"Ошибка при генерации {e}"
