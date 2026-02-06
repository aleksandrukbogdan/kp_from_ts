"""
Скрипт для очистки и нормализации reference_data.json.
Удаляет мусорные строки, нормализует названия этапов.
"""

import json
import re
from pathlib import Path

INPUT_FILE = "reference_data.json"
OUTPUT_FILE = "reference_data_clean.json"

# Нормализация названий этапов
STAGE_NORMALIZATION = {
    # Бэкенд/Фронтенд
    "Бэкенд": "Бэкенд разработка",
    "Фронтенд": "Фронтенд разработка",
    
    # Проектирование
    "Проектирование / аналитика / прототипирование": "Проектирование и аналитика",
    "Проектирование/аналитика/прототипирование": "Проектирование и аналитика",
    
    # Обработка данных
    "Обработка данных (ETL / ML / LLM)": "Обработка данных",
}

# Мусорные этапы - удалить полностью
GARBAGE_STAGES = {
    "Этапы",
}


def normalize_stage_name(name: str) -> str:
    """Нормализует название этапа."""
    name = name.strip()
    
    # Удаляем нумерацию в начале: "1) ", "2) ", "10) " и т.д.
    name = re.sub(r'^\d+\)\s*', '', name)
    
    # Удаляем указание недель в скобках в конце: "(2 недели)", "(3 недели)"
    name = re.sub(r'\s*\(\d+\s*недел[ияь]\)$', '', name)
    name = re.sub(r'\s*\(LDE,\s*РП\)$', '', name)
    
    # Применяем словарь нормализации
    if name in STAGE_NORMALIZATION:
        name = STAGE_NORMALIZATION[name]
    
    return name.strip()


def has_hours(hours: dict) -> bool:
    """Проверяет, есть ли ненулевые часы."""
    return any(v > 0 for v in hours.values() if isinstance(v, (int, float)))


def clean_project(project: dict) -> dict:
    """Очищает один проект."""
    clean_stages = []
    seen_stages = {}  # Для агрегации дублей
    
    for stage in project.get("stages", []):
        stage_name = stage.get("stage", "")
        
        # Пропускаем мусорные этапы
        if stage_name in GARBAGE_STAGES:
            continue
        
        # Пропускаем этапы без часов
        if not has_hours(stage.get("hours", {})):
            continue
        
        # Нормализуем название
        normalized_name = normalize_stage_name(stage_name)
        
        # Агрегируем дубли (суммируем часы)
        if normalized_name in seen_stages:
            existing = seen_stages[normalized_name]
            for role, hours in stage.get("hours", {}).items():
                if hours > 0:
                    existing["hours"][role] = existing["hours"].get(role, 0) + hours
            # Объединяем описания если разные
            new_desc = stage.get("description", "").strip()
            if new_desc and new_desc not in existing.get("description", ""):
                existing["description"] = (existing.get("description", "") + "; " + new_desc).strip("; ")
        else:
            seen_stages[normalized_name] = {
                "stage": normalized_name,
                "description": stage.get("description", "").strip(),
                "hours": stage.get("hours", {}).copy()
            }
    
    return {
        "project_name": project["project_name"],
        "rates": project["rates"],
        "stages": list(seen_stages.values())
    }


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Очищаем проекты
    clean_projects = []
    for project in data.get("projects", []):
        cleaned = clean_project(project)
        if cleaned["stages"]:  # Только если остались этапы
            clean_projects.append(cleaned)
            print(f"✓ {cleaned['project_name']}: {len(cleaned['stages'])} этапов")
    
    # Собираем уникальные нормализованные этапы
    all_stages = set()
    for proj in clean_projects:
        for stage in proj["stages"]:
            all_stages.add(stage["stage"])
    
    # Формируем очищенный справочник
    clean_data = {
        "rates": data.get("rates", {}),
        "common_stages": sorted(list(all_stages)),
        "projects": clean_projects
    }
    
    # Сохраняем
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Сохранено в {OUTPUT_FILE}")
    print(f"  Проектов: {len(clean_projects)}")
    print(f"  Уникальных этапов: {len(all_stages)}")
    
    # Заменяем оригинал
    Path(INPUT_FILE).rename(INPUT_FILE + ".bak")
    Path(OUTPUT_FILE).rename(INPUT_FILE)
    print(f"  Оригинал сохранен как {INPUT_FILE}.bak")


if __name__ == "__main__":
    main()
