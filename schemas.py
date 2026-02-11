from typing import List, Literal, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator

# --- Helper Validator ---
def string_to_source_text(v: Any) -> Any:
    """Converts various LLM outputs to a SourceText-compatible dict."""
    if v is None:
        return {"text": ""}
    
    # helper to clean python-repr strings like "text='foo' source='bar'"
    def clean_repr_string(s):
        if isinstance(s, str):
            import re
            # Regex to catch:
            # text='...' or text="..."
            # Text='...' (case insensitive key)
            # text = '...' (spaces)
            # Also handle if the string starts with just '...' (quoted)
            
            # Pattern: look for text\s*=\s*['"](.*?)['"]
            # But be careful about greedy matching if there are multiple fields.
            # Lazy match .*? is key.
            match = re.search(r"(?:text|feature)\s*[:=]\s*['\"](.*?)['\"]", s, re.IGNORECASE)
            if match:
                return {"text": match.group(1)}
                
            # Fallback: if input is literally "'Value'", strip quotes
            if s.startswith("'") and s.endswith("'") and len(s) > 1:
                return {"text": s[1:-1]}
            if s.startswith('"') and s.endswith('"') and len(s) > 1:
                return {"text": s[1:-1]}
                
            # If no pattern, just return the string as is (cleaning happens later if needed)
            return None
        return None

    if isinstance(v, str):
        cleaned = clean_repr_string(v)
        if cleaned:
            return cleaned
        return {"text": v.strip()}

    if isinstance(v, dict):
        text = v.get("text") or v.get("name") or v.get("value") or ""
        
        if isinstance(text, str):
            cleaned_text = clean_repr_string(text)
            if cleaned_text:
                text = cleaned_text["text"]

        if isinstance(text, list):
            text = text[0] if text else ""
            
        return {"text": str(text).strip()}

    # Check if it's an object with a text attribute (e.g. already a SourceText model)
    if hasattr(v, "text"):
        return {"text": v.text}
        
    return {"text": str(v).strip()}

# --- Pydantic Models for Structured Output ---
class SourceText(BaseModel):
    text: str = Field(description="Текст значения (Описание требования или технологии). НА РУССКОМ ЯЗЫКЕ.")
    source_quote: Optional[str] = Field(default=None, description="Цитата из исходного текста, подтверждающая требование.")
    page_number: Optional[int] = Field(default=None, description="Номер страницы с цитатой.")


class KeyFeaturesDetails(BaseModel):
    # Use aliases for common LLM mistakes if needed, but 'before' validator is better for lists vs dicts
    modules: List[SourceText] = Field(default_factory=list, description="Логические модули системы.")
    screens: List[SourceText] = Field(default_factory=list, description="UI-экраны, формы.")
    reports: List[SourceText] = Field(default_factory=list, description="Отчёты, аналитика.")
    integrations: List[SourceText] = Field(default_factory=list, description="Интеграции.")
    nfr: List[SourceText] = Field(default_factory=list, description="НФТ.")

    @model_validator(mode='before')
    @classmethod
    def flatten_extracted_list(cls, data: Any) -> Any:
        # Sometimes LLM returns a list of items instead of a dict with categories
        if isinstance(data, list):
            new_data = {
                "modules": [], "screens": [], "reports": [], "integrations": [], "nfr": []
            }
            for item in data:
                text = ""
                source = ""
                category = "modules" # default
                
                if isinstance(item, dict):
                    # Handle various keys the LLM might use
                    text = item.get("feature") or item.get("text")
                    
                    # Handle {name: ..., description: ...} case
                    if not text and item.get("name") and item.get("description"):
                        text = f"{item['name']}: {item['description']}"
                    elif not text:
                        # If still no text, use values
                        parts = [str(v) for k,v in item.items() if k not in ["category", "source", "estimated_hours", "hours"]]
                        if parts:
                            text = " ".join(parts)
                        else:
                            text = str(item)

                if text:
                    new_data[category].append({"text": text})
            return new_data
        return data
    
    @field_validator("*", mode="before")
    @classmethod
    def parse_list_items(cls, v):
        if isinstance(v, list):
            return [string_to_source_text(item) for item in v]
        return v

class ExtractedTZData(BaseModel):
    reasoning: str = Field(default="", description="Сначала напиши свои рассуждения: 1. Что это за документ? 2. Какие ключевые модули ты видишь? 3. Есть ли тут конкретный стек?")
    client_name: SourceText = Field(default_factory=lambda: SourceText(text=""), description="Название клиента.")
    project_essence: SourceText = Field(default_factory=lambda: SourceText(text=""), description="Краткая суть проекта.")
    project_type: SourceText = Field(default_factory=lambda: SourceText(text="Other"), description="Тип проекта: Web, Mobile, ERP, CRM, AI, Integration, Other.")
    
    business_goals: List[SourceText] = Field(default_factory=list, description="Бизнес-цели")
    tech_stack: List[SourceText] = Field(default_factory=list, description="Стек")
    client_integrations: List[SourceText] = Field(default_factory=list, description="Интеграции")
    
    key_features: KeyFeaturesDetails = Field(default_factory=KeyFeaturesDetails, description="Функциональные требования.")

    @field_validator("business_goals", "tech_stack", "client_integrations", mode="before")
    @classmethod
    def validate_source_text_list(cls, v):
        if not isinstance(v, list):
            return []
        return [string_to_source_text(item) for item in v]

    @field_validator("client_name", "project_essence", "project_type", mode="before")
    @classmethod
    def validate_source_text_fields(cls, v):
        if isinstance(v, list):
            if not v:
                return SourceText(text="", source="")
            return string_to_source_text(v[0])
        return string_to_source_text(v)


# --- Phase 2 Models ---
class RequirementIssue(BaseModel):
    type: str = Field(default="questionable")
    field: str = Field(default="key_features")
    category: str = Field(default="general")
    item_text: str = Field(default="Unknown Issue")
    source: str = Field(default="")
    reason: str = Field(default="No reason provided")
    
    @model_validator(mode='before')
    @classmethod
    def normalize_issue(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"item_text": data, "reason": "Extracted as text"}
        
        # Clean item_text if it looks like "text='...' source='...'"
        if isinstance(data, dict):
            text = data.get("item_text", "")
            if text and ("text='" in text or 'text="' in text):
                import re
                # Try to extract the 'text' part
                match = re.search(r"text=['\"](.*?)['\"]", text)
                if match:
                    data["item_text"] = match.group(1)
        return data

class FeatureEstimate(BaseModel):
    feature_text: str = Field(alias="text") # Handle 'text' alias
    hours: int = Field(default=5)
    
    @model_validator(mode='before')
    @classmethod
    def fallback(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sometimes LLM sends "feature": "Name", "estimate": 10
            if "feature" in data and "feature_text" not in data:
                data["feature_text"] = data["feature"]
            if "text" in data and "feature_text" not in data:
                 data["feature_text"] = data["text"]
        return data

class AnalysisTZResult(BaseModel):
    requirement_issues: List[RequirementIssue] = Field(default_factory=list)
    suggested_stages: List[str] = Field(default_factory=list)
    suggested_roles: List[str] = Field(default_factory=list)
    estimates: List[FeatureEstimate] = Field(default_factory=list)
    
    @field_validator("estimates", mode="before")
    @classmethod
    def validate_estimates(cls, v):
        if isinstance(v, dict):
             # Handle dict format {"Feature": 10}
             return [{"feature_text": key, "hours": val} for key, val in v.items()]
        return v

# --- Phase 3 & 4 Models ---
class RoleEstimate(BaseModel):
    role_name: str = Field(default="Unknown Role")
    hours: int = Field(default=0)
    
    @model_validator(mode='before')
    @classmethod
    def fix_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "role" in data and "role_name" not in data:
                data["role_name"] = data["role"]
        return data

class StageEstimate(BaseModel):
    stage_name: str = Field(default="Unknown Stage")
    role_estimates: List[RoleEstimate] = Field(default_factory=list, alias="roles") # 'roles' common alias
    
    @model_validator(mode='before')
    @classmethod
    def fix_keys_and_structure(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Name aliases
            if "name" in data and "stage_name" not in data:
                data["stage_name"] = data["name"]
            if "stage" in data and "stage_name" not in data:
                data["stage_name"] = data["stage"]
                
            # Roles alias fallback (if needed beyond alias field)
            if "roles" in data and "role_estimates" not in data:
                data["role_estimates"] = data["roles"]
                
        return data

class BudgetResult(BaseModel):
    stages: List[StageEstimate] = Field(default_factory=list)


# --- Phase 1.5 Models (Detailed Analysis) ---
class RequirementAnalysisItem(BaseModel):
    category: str = Field(description="Тип требования (например: Безопасность, Интерфейс, Бэкенд, Бизнес-логика)")
    summary: str = Field(description="Краткое, четкое описание требования своими словами (для менеджера)")
    search_query: str = Field(description="Уникальный фрагмент текста из источника для векторного поиска (для BGE-M3)")
    importance: Literal["Высокая", "Средняя", "Низкая"] = Field(description="Важность требования")
    
    # RAG Enriched Fields (Filled later)
    source_text: Optional[str] = Field(default=None, description="Найденный 'Reverse RAG' текст из документа")
    page_number: Optional[int] = Field(default=None, description="Номер страницы")
    bbox: Optional[str] = Field(default=None, description="Координаты BBox на странице")
    confidence_score: Optional[float] = Field(default=None, description="Оценка уверенности поиска")

class RequirementAnalysisResult(BaseModel):
    items: List[RequirementAnalysisItem] = Field(default_factory=list)

class ProposalResult(BaseModel):
    markdown_content: str = Field(description="Markdown текст КП")

# --- Manager Notes Classification ---
class ManagerNoteItem(BaseModel):
    text: str = Field(description="Краткая формулировка требования менеджера. НА РУССКОМ ЯЗЫКЕ.")
    category: Literal[
        "business_goal", "tech_stack", "integration",
        "module", "screen", "report", "nfr"
    ] = Field(description="Категория требования: business_goal (бизнес-цель), tech_stack (технология), integration (интеграция), module (модуль/функция), screen (экран/UI), report (отчёт), nfr (нефункциональное)")

class ManagerNotesResult(BaseModel):
    items: List[ManagerNoteItem] = Field(default_factory=list, description="Список классифицированных требований менеджера")
