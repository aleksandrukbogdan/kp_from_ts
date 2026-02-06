"""
Скрипт для парсинга Excel-справочника проектов.
Извлекает этапы, описания, часы по ролям и ставки.
Сохраняет в reference_data.json для использования в LLM.
"""

import pandas as pd
import json
from pathlib import Path

EXCEL_FILE = "Расчеты по проектам.xlsx"
OUTPUT_FILE = "reference_data.json"

# Стандартные роли и их ставки (из первой строки Excel)
DEFAULT_RATES = {
    "Менеджер": 1700,
    "ML-инженер": 1200,
    "Тестировщик": 1600
}

def parse_sheet(df: pd.DataFrame, sheet_name: str) -> dict:
    """Парсит один лист Excel и возвращает структурированные данные."""
    
    stages = []
    rates = DEFAULT_RATES.copy()
    
    # Первая строка обычно содержит ставки
    first_row = df.iloc[0]
    if pd.notna(first_row.get("Менеджер")):
        rates["Менеджер"] = float(first_row["Менеджер"])
    if pd.notna(first_row.get("ML-инженер")):
        rates["ML-инженер"] = float(first_row["ML-инженер"])
    if pd.notna(first_row.get("Тестировщик")):
        # Тестировщик может быть числом или строкой
        val = first_row.get("Тестировщик")
        if isinstance(val, (int, float)) and pd.notna(val):
            rates["Тестировщик"] = float(val)
    
    # Парсим строки с этапами (пропускаем NaN в колонке Этапы)
    for idx, row in df.iterrows():
        stage_name = row.get("Этапы")
        
        # Пропускаем строки без названия этапа или итоговые строки
        if pd.isna(stage_name) or not str(stage_name).strip():
            continue
        
        stage_name = str(stage_name).strip()
        
        # Пропускаем служебные строки
        if stage_name in ["Итого без НДС:", "НДС", "Итого с НДС"]:
            continue
        
        description = row.get("Описание/кол-во", "")
        if pd.isna(description):
            description = ""
        description = str(description).strip()
        
        # Часы по ролям
        hours = {}
        for role in ["Менеджер", "ML-инженер", "Тестировщик"]:
            val = row.get(role, 0)
            if pd.notna(val) and isinstance(val, (int, float)):
                hours[role] = float(val)
            else:
                hours[role] = 0
        
        stages.append({
            "stage": stage_name,
            "description": description,
            "hours": hours
        })
    
    return {
        "project_name": sheet_name,
        "rates": rates,
        "stages": stages
    }


def main():
    excel_path = Path(EXCEL_FILE)
    if not excel_path.exists():
        print(f"Файл {EXCEL_FILE} не найден!")
        return
    
    xl = pd.ExcelFile(excel_path)
    
    all_projects = []
    all_stages_set = set()  # Уникальные этапы
    
    for sheet_name in xl.sheet_names:
        # Пропускаем служебные листы
        if sheet_name.lower() in ["стоимость часов"]:
            continue
            
        df = pd.read_excel(xl, sheet_name)
        
        # Проверяем что это лист с нужной структурой
        if "Этапы" not in df.columns:
            print(f"Пропускаем лист {sheet_name} - нет колонки 'Этапы'")
            continue
        
        project_data = parse_sheet(df, sheet_name)
        all_projects.append(project_data)
        
        # Собираем уникальные этапы
        for stage in project_data["stages"]:
            all_stages_set.add(stage["stage"])
        
        print(f"✓ {sheet_name}: {len(project_data['stages'])} этапов")
    
    # Формируем итоговый справочник
    reference = {
        "rates": DEFAULT_RATES,
        "common_stages": sorted(list(all_stages_set)),
        "projects": all_projects
    }
    
    # Сохраняем в JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(reference, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Сохранено в {OUTPUT_FILE}")
    print(f"  Проектов: {len(all_projects)}")
    print(f"  Уникальных этапов: {len(all_stages_set)}")
    print(f"  Ставки: {DEFAULT_RATES}")


if __name__ == "__main__":
    main()
