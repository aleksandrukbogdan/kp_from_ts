
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
import logging

# Suppress annoying RapidOCR warnings
logging.getLogger("RapidOCR").setLevel(logging.ERROR)
logging.getLogger("rapidocr").setLevel(logging.ERROR)

# New Modules
from llm_service import LLMService
from schemas import (
    ExtractedTZData, 
    AnalysisTZResult, 
    BudgetResult, 
    ProposalResult, 
    KeyFeaturesDetails,
    SourceText,
    RequirementAnalysisResult,
    RequirementAnalysisItem,
    ManagerNotesResult
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
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
            
            is_dev = os.getenv("IS_DEV", "false").lower() == "true"
            
            # Setup Pipeline with potential CUDA support
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True
            
            # Smart Device Selection
            try:
                import torch
                if not is_dev and torch.cuda.is_available():
                     device = AcceleratorDevice.CUDA
                     print("Docling: Using CUDA (H100/GPU detected).")
                else:
                     device = AcceleratorDevice.CPU
                     print("Docling: Using CPU.")
            except ImportError:
                 device = AcceleratorDevice.CPU
                 print("Docling: Torch generic check failed, using CPU.")
            
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=32, device=device
            )

            _doc_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            print("Docling initialized successfully.")

        except ImportError as e:
            print(f"Docling Import Error: {e}. Check if 'docling' is in requirements.txt and installed.")
            # We can't return a converter if we can't import the class, so we might return None or raise
            # But the fallback below uses DocumentConverter() which ALSO needs the import? 
            # If import fails, we are dead in the water for Docling.
            # But maybe the user has an old version? 
            # Re-raising ensures we see the log.
            # However, to be safe for the 'parse_file_activity' let's allow it to fail there or return a dummy if completely missing.
            # Raising is better so the user knows.
            raise RuntimeError(f"Docling libraries missing: {e}") from e

        except Exception as e:
            print(f"Docling Init Error (Configuration): {e}. Attempting fallback to default CPU config.")
            try:
                # Fallback to simplest possible init
                _doc_converter = DocumentConverter()
                print("Docling fallback initialized.")
            except Exception as e2:
                print(f"Docling Fallback Failed: {e2}")
                raise e2
        
        return _doc_converter

def _convert_docx_to_pdf(docx_path: Path) -> Path:
    """Convert DOCX to PDF using LibreOffice. Returns path to PDF file."""
    import subprocess
    
    output_dir = docx_path.parent
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    
    # LibreOffice command for headless conversion
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(output_dir),
        str(docx_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"LibreOffice conversion failed: {result.stderr}")
            return None
        
        if pdf_path.exists():
            print(f"DOCX→PDF conversion successful: {pdf_path}")
            return pdf_path
        else:
            print(f"PDF file not created at expected path: {pdf_path}")
            return None
    except subprocess.TimeoutExpired:
        print("LibreOffice conversion timed out (120s)")
        return None
    except FileNotFoundError:
        print("LibreOffice not found. Install with: apt install libreoffice-writer")
        return None
    except Exception as e:
        print(f"DOCX→PDF conversion error: {e}")
        return None


@activity.defn
async def parse_file_activity(file_path: str, file_name: str, convert_to_pdf_for_pages: bool = True) -> str:
    """Parses document via Docling and saves Markdown to a file. Returns path to MD file.
    
    Args:
        file_path: Path to the document
        file_name: Original filename
        convert_to_pdf_for_pages: If True, converts DOCX to PDF before parsing to enable page number extraction
    """
    doc_converter = get_docling_converter()
    input_path = Path(file_path)
    original_path = input_path  # Keep for reference

    # DOCX → PDF conversion for page numbers
    if convert_to_pdf_for_pages and file_path.lower().endswith(('.docx', '.doc')):
        activity.logger.info(f"Converting DOCX to PDF for page number extraction: {file_path}")
        pdf_path = await asyncio.to_thread(_convert_docx_to_pdf, input_path)
        if pdf_path:
            input_path = pdf_path
            activity.logger.info(f"Using converted PDF: {pdf_path}")
        else:
            activity.logger.warning("DOCX→PDF conversion failed, continuing with original DOCX (no page numbers)")

    try:
        activity.logger.info(f"Docling: Starting parsing for {input_path}...")
        
        # Offload CPU-bound task to a separate thread to prevent blocking Temporal heartbeat
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
    
    # Save Markdown
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    # Save Docling JSON (for RAG Metadata)
    try:
        json_filename = f"{input_path.stem}_parsed.json"
        json_path = input_path.parent / json_filename
        # docling export_to_dict returns a dict, needed for detailed layout info
        doc_dict = result.document.export_to_dict()
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(doc_dict, f, ensure_ascii=False, default=str)
    except Exception as e:
        activity.logger.error(f"Failed to save Docling JSON: {e}")
        
    return str(md_path)

@activity.defn
async def ocr_document_activity(file_path: str) -> str:
    """Fallback OCR if standard parsing fails. Handles Images and PDFs."""
    try:
        import mimetypes
        from pdf2image import convert_from_path

        # Determine if it's a PDF
        mime_type, _ = mimetypes.guess_type(file_path)
        is_pdf = mime_type == 'application/pdf' or file_path.lower().endswith('.pdf')
        
        images_to_process = []
        
        if is_pdf:
            activity.logger.info(f"OCR: Converting PDF to images: {file_path}")
            # Convert first 5 pages max to avoid overload
            # fmt='jpeg' matches the data url we generally use
            try:
                images = convert_from_path(file_path, first_page=1, last_page=5, fmt='jpeg')
                for img in images:
                    # Save to bytes
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG')
                    images_to_process.append(buf.getvalue())
            except Exception as e:
                activity.logger.error(f"PDF to Image Conversion failed: {e}")
                return ""
        else:
            # Assume it's an image file
            with open(file_path, "rb") as f:
                images_to_process.append(f.read())

        combined_text = ""
        llm = LLMService()

        # Process each page/image
        for i, img_bytes in enumerate(images_to_process):
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Page {i+1}. Transcribe ALL text from this image exactly as it appears. Detect layout if possible."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            }]
            
            try:
                text = await llm.create_chat_completion(messages=messages)
                combined_text += f"\n\n--- Page {i+1} ---\n\n{text}"
            except Exception as e:
                activity.logger.error(f"OCR Failed for page {i+1}: {e}")

        if not combined_text:
            return ""

        # Save OCR result to file
        input_path = Path(file_path)
        md_path = input_path.parent / f"{input_path.stem}_ocr.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(combined_text)
            
        return str(md_path)
        
    except Exception as e:
        activity.logger.error(f"OCR Activity Error: {e}")
        return "" # Signal failure

@activity.defn
async def save_budget_stub(data: dict) -> str:
    """Stub for database saving."""
    print(f'Stub saving to Postgres: {data}')
    return "ok"

def _load_reference_data() -> dict:
    """Загружает справочные данные из JSON (парсинг Расчёты по проектам.xlsx)."""
    reference_path = Path(__file__).parent / "reference_data.json"
    if not reference_path.exists():
        return {}
    try:
        with open(reference_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load reference_data.json: {e}")
        return {}

def _format_reference_for_prompt(reference: dict, max_projects: int = 3) -> str:
    """Форматирует справочные данные для включения в промпт LLM."""
    if not reference or "projects" not in reference:
        return ""
    
    lines = ["СПРАВОЧНИК КОМПАНИИ (исторические данные по проектам):"]
    lines.append(f"Типовые ставки: Менеджер={reference.get('rates', {}).get('Менеджер', 1700)}₽/ч, "
                 f"ML-инженер={reference.get('rates', {}).get('ML-инженер', 1200)}₽/ч, "
                 f"Тестировщик={reference.get('rates', {}).get('Тестировщик', 1600)}₽/ч")
    lines.append("")
    
    for proj in reference.get("projects", [])[:max_projects]:
        lines.append(f"## {proj['project_name']}")
        for stage in proj.get("stages", []):
            hours = stage.get("hours", {})
            hours_str = ", ".join([f"{r}:{h}ч" for r, h in hours.items() if h > 0])
            if hours_str:
                lines.append(f"  - {stage['stage']}: {hours_str}")
        lines.append("")
    
    return "\n".join(lines)

@activity.defn
async def estimate_hours_activity(tz_data: dict, stages: list, roles: list, additional_notes: str = "") -> dict:
    """
    Generates Budget Matrix: Stage -> Role -> Hours
    Uses reference_data.json as context for more accurate estimates.
    """
    llm = LLMService()
    
    # Load reference data from parsed Excel
    reference = _load_reference_data()
    reference_context = _format_reference_for_prompt(reference)
    
    try:
        activity.logger.info("Starting Budget Estimation with reference data")
        
        system_prompt = """Ты Project Manager с доступом к историческим данным компании.
Оцени трудозатраты в часах для каждого этапа и роли.

ПРАВИЛА:
1. Используй ТОЛЬКО предложенные этапы и роли.
2. Ориентируйся на справочные данные компании — там реальные часы с прошлых проектов.
3. Если этап похож на типовой из справочника — бери часы оттуда как базу.
4. Если этап уникален — оценивай по аналогии с похожими.
5. Отвечай на РУССКОМ."""

        # Optimization: Extract only text, stripping large RAG quotes
        p_essence = tz_data.get('project_essence')
        p_essence_txt = p_essence.get('text', str(p_essence)) if isinstance(p_essence, dict) else str(p_essence)

        t_stack = tz_data.get('tech_stack', [])
        t_stack_txt = []
        if isinstance(t_stack, list):
            for item in t_stack:
                val = item.get('text', str(item)) if isinstance(item, dict) else str(item)
                t_stack_txt.append(val)
        t_stack_str = ", ".join(t_stack_txt)

        user_prompt = f"""{reference_context}

ТЕКУЩИЙ ПРОЕКТ:
Суть: {p_essence_txt}
Стек: {t_stack_str}
{f'''
Дополнительные указания заказчика:
{additional_notes}''' if additional_notes else ''}

Этапы (stages): {stages}
Роли (roles): {roles}

Заполни матрицу часов:
Для КАЖДОГО этапа из списка Stages укажи часы для КАЖДОЙ роли из списка Roles.
Если роль не участвует в этапе, ставь 0.
Опирайся на справочные данные выше!"""

        budget_result: BudgetResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
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
async def generate_proposal_activity(data: dict, budget_matrix: dict, rates: dict, additional_notes: str = "") -> str:
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
        # Optimization: Prepare prompt data by stripping large source quotes (without mutating original)
        def _get_text(val):
            if isinstance(val, dict):
                return val.get('text', str(val))
            return str(val)
            
        def _get_list_text(val_list):
            if isinstance(val_list, list):
                return ", ".join([_get_text(v) for v in val_list])
            return str(val_list)

        p_essence = _get_text(data.get('project_essence', ''))
        b_goals = _get_list_text(data.get('business_goals', []))
        t_stack = _get_list_text(data.get('tech_stack', []))
        
        # Format Key Features (Complex nested structure)
        k_features = data.get('key_features', {})
        k_features_txt = ""
        if isinstance(k_features, dict):
            for category, items in k_features.items():
                if items:
                     k_features_txt += f"\n- {category}: {_get_list_text(items)}"
        else:
             k_features_txt = str(k_features)

        proposal: ProposalResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": "Ты Менеджер по продажам. Напиши убедительное Коммерческое Предложение в формате Markdown на РУССКОМ языке."},
                {"role": "user", "content": f"""
Суть проекта: {p_essence}
Цели: {b_goals}
Функционал: {k_features_txt}
Стек: {t_stack}
{f'''
Дополнительные указания заказчика (учти в КП):
{additional_notes}''' if additional_notes else ''}

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
    # Optimization: Increased default chunk size for large-context models (e.g. Qwen3-VL 128k)
    # 50,000 bytes ~ 15k tokens. Safe for 32k+ context windows.
    CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", 50000))
    OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", 2000))
    
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
async def index_document_activity(md_file_path: str) -> List[Dict[str, Any]]:
    """
    1. Splits markdown for LLM processing (returning chunk defs).
    2. Indexes the rich content (JSON) into LanceDB for RAG.
    """
    # 1. Standard Split for LLM (keep existing logic)
    chunks_defs = await asyncio.to_thread(_split_text_sync, md_file_path)
    
    # 2. RAG Indexing
    def _run_indexing():
        try:
            # Look for the JSON file we saved earlier
            input_path = Path(md_file_path)
            json_path = input_path.parent / f"{input_path.stem.replace('_parsed', '')}_parsed.json"
            
            rag_chunks = []
            
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Iterate over Docling structure to create RAG chunks
                # Docling dict structure: 'pages', 'texts' or 'main_text'
                # Simplified approach: Iterate 'texts' if available or fallback to parsing the MD logic again
                # Assuming 'texts' contains paragraph-level info with provenance
                
                # If Docling export format is complex, we might just chunk the tokens. 
                # For this MVP: Use the 'texts' array if present, usually distinct elements.
                if 'texts' in data:
                     for item in data['texts']:
                         # item structure depends on version:
                         # {'text': '...', 'prov': [{'page_no': 1, 'bbox': ...}]} OR
                         # {'text': '...', 'prov': [{'page': 1, 'bbox': ...}]}
                         text_content = item.get('text', '').strip()
                         if len(text_content) > 20: # Skip noise
                             prov_list = item.get('prov') or [{}]
                             prov = prov_list[0]
                             # Try multiple possible keys for page number
                             page_num = prov.get('page_no') or prov.get('page_number') or prov.get('page') or 0
                             rag_chunks.append({
                                 "text": text_content,
                                 "page_number": page_num,
                                 "bbox": str(prov.get('bbox', [])),
                                 "source_file": str(input_path.name)
                             })
            
            # Fallback if no JSON or empty: Chunk the MD lines
            if not rag_chunks:
                activity.logger.warning("No structured JSON found for RAG. Using text chunks.")
                # We can reuse the chunks_defs logic but we need the actual text
                with open(md_file_path, "r", encoding="utf-8") as f:
                    full_text = f.read()
                
                # Create simple chunks
                for c in chunks_defs:
                    txt = full_text[c['start']:c['end']]
                    rag_chunks.append({
                        "text": txt,
                        "page_number": 0,
                        "bbox": "",
                        "source_file": str(input_path.name)
                    })

            # Create Index
            from rag_service import RAGService
            rag = RAGService()
            # Use workflow_id as the table name for isolation
            wf_id = activity.info().workflow_id
            # Sanitize just in case, though Temporal IDs are usually safe strings
            table_name = f"req_{wf_id.replace('-', '_')}"
            
            rag.create_index(chunks=rag_chunks, table_name=table_name)
            
            return {
                "status": "indexed", 
                "chunks_count": len(rag_chunks),
                "table_name": table_name
            }
        except Exception as e:
            activity.logger.error(f"Indexing Failed: {e}")
            return {
                "status": "failed",
                "chunks_count": 0,
                "table_name": None,
                "error": str(e)
            }
            
    await asyncio.to_thread(_run_indexing)
    
    return chunks_defs

@activity.defn
async def refine_requirements_activity(requirements: List[dict]) -> List[dict]:
    """
    Phase 3: Reverse RAG.
    Enriches requirements with exact source text via Vector Search.
    """
    from rag_service import RAGService
    rag = RAGService()
    wf_id = activity.info().workflow_id
    table_name = f"req_{wf_id.replace('-', '_')}"
    
    refined_list = []
    
    for item_dict in requirements:
        try:
            # Rehydrate model
            item = RequirementAnalysisItem(**item_dict)
            
            if item.search_query:
                matches = await asyncio.to_thread(rag.search, item.search_query, table_name=table_name, top_k=1)
                
                if matches:
                    top_match = matches[0]
                    # Update Item
                    item.source_text = top_match.get('text', '')
                    item.page_number = top_match.get('page_number')
                    item.bbox = top_match.get('bbox')
                    # LanceDB returns '_distance' usually, convert to score if needed
                    item.confidence_score = 0.95 # Mock/Placeholder or calc from distance
            
            refined_list.append(item.model_dump())
            
        except Exception as e:
            activity.logger.error(f"Refinement Failed for item: {e}")
            refined_list.append(item_dict) # Keep original on error

    return refined_list


@activity.defn
async def enrich_with_rag_activity(merged_data: dict) -> dict:
    """
    Enriches all SourceText items with RAG source quotes.
    Uses the item's 'text' field as the search query (NotebookLM-style).
    """
    from rag_service import RAGService
    rag = RAGService()
    wf_id = activity.info().workflow_id
    table_name = f"req_{wf_id.replace('-', '_')}"
    
    activity.logger.info(f"Starting RAG enrichment for all fields...")
    
    async def enrich_item(item: dict) -> dict:
        """Enrich a single SourceText item with RAG lookup."""
        if not item or not isinstance(item, dict):
            return item
        
        # Skip items already tagged as manager requirements
        if item.get('source_quote') == 'Требование менеджера' or item.get('source') == 'Требование менеджера':
            return item
        
        query = item.get('text', '')
        if not query or len(query) < 5:  # Skip very short queries
            return item
        
        try:
            matches = await asyncio.to_thread(rag.search, query, table_name=table_name, top_k=1)
            
            if matches:
                match = matches[0]
                # Calculate confidence from distance (lower distance = higher confidence)
                distance = match.get('_distance', 0.5)
                confidence = max(0.0, 1.0 - distance)
                
                # Only enrich if we have a good match (confidence > 0.3)
                if confidence > 0.3:
                    item['source_quote'] = match.get('text', '')
                    item['page_number'] = match.get('page_number')
                    item['rag_confidence'] = round(confidence, 2)
        except Exception as e:
            activity.logger.warning(f"RAG lookup failed for '{query[:50]}...': {e}")
        
        return item
    
    # Enrich simple list fields
    for field in ['business_goals', 'tech_stack', 'client_integrations']:
        items = merged_data.get(field, [])
        if isinstance(items, list):
            enriched_items = []
            for item in items:
                enriched_items.append(await enrich_item(item))
            merged_data[field] = enriched_items
    
    # Enrich key_features (nested structure with categories)
    key_features = merged_data.get('key_features', {})
    if isinstance(key_features, dict):
        for category, items in key_features.items():
            if isinstance(items, list):
                enriched_items = []
                for item in items:
                    enriched_items.append(await enrich_item(item))
                key_features[category] = enriched_items
        merged_data['key_features'] = key_features
    
    activity.logger.info("RAG enrichment complete.")
    return merged_data

@activity.defn
async def classify_manager_notes_activity(additional_notes: str, merged_data: dict) -> dict:
    """
    Dedicated activity: classifies manager's free-text notes into structured items.
    Uses a flat list schema (text + category enum) — simple for LLM.
    Code maps categories to merged_data fields deterministically.
    """
    if not additional_notes or not additional_notes.strip():
        return merged_data
    
    llm = LLMService()
    MANAGER_TAG = "Требование менеджера"
    
    try:
        activity.logger.info(f"Classifying manager notes ({len(additional_notes)} chars)...")
        
        system_prompt = """Ты Системный Аналитик. Тебе дан свободный текст с указаниями менеджера проекта.

Твоя задача: разбить текст на отдельные требования и классифицировать каждое.

Для каждого требования выбери ОДНУ категорию:
- business_goal — бизнес-цель ("увеличить продажи", "выйти на новый рынок")
- tech_stack — технология ("PostgreSQL", "React", "Docker")
- integration — интеграция с внешней системой ("1С", "Bitrix", "SAP")
- module — функциональный модуль или функция ("авторизация", "каталог товаров")
- screen — экран, форма, UI-компонент ("дашборд", "форма заказа")
- report — отчёт или аналитика ("отчёт по продажам")
- nfr — нефункциональное требование ("время отклика < 2с", "без тестировщика")

ПРАВИЛА:
1. Одно указание = один пункт. Не дублируй.
2. Если не уверен в категории — ставь module.
3. Формулируй кратко и чётко.
4. Отвечай на РУССКОМ."""
        
        result: ManagerNotesResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Указания менеджера:\n\n{additional_notes}"}
            ],
            output_model=ManagerNotesResult,
            tool_name="classify_manager_notes"
        )
        
        # Deterministic mapping: category → merged_data location
        CATEGORY_MAP = {
            "business_goal": ("business_goals", None),
            "tech_stack":    ("tech_stack", None),
            "integration":   ("client_integrations", None),
            "module":        ("key_features", "modules"),
            "screen":        ("key_features", "screens"),
            "report":        ("key_features", "reports"),
            "nfr":           ("key_features", "nfr"),
        }
        
        for item in result.items:
            tagged_item = {"text": item.text, "source_quote": MANAGER_TAG}
            field, sub_field = CATEGORY_MAP.get(item.category, ("key_features", "modules"))
            
            if sub_field is None:
                # Top-level list (business_goals, tech_stack, client_integrations)
                if field not in merged_data or not isinstance(merged_data[field], list):
                    merged_data[field] = []
                merged_data[field].append(tagged_item)
            else:
                # Nested under key_features
                if 'key_features' not in merged_data or not isinstance(merged_data['key_features'], dict):
                    merged_data['key_features'] = {}
                kf = merged_data['key_features']
                if sub_field not in kf or not isinstance(kf[sub_field], list):
                    kf[sub_field] = []
                kf[sub_field].append(tagged_item)
        
        activity.logger.info(f"Manager notes: {len(result.items)} items classified and merged.")
        return merged_data
        
    except Exception as e:
        activity.logger.error(f"Manager Notes Classification Failed: {e}")
        return merged_data  # Return unchanged on error

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
- project_type: Выбери один вариант, который ЛУЧШЕ ВСЕГО подходит: [Web, Mobile, ERP, CRM, AI, Интеграции, Прочее].
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

@activity.defn
async def analyze_requirements_chunk_activity(chunk_def: Dict[str, Any]) -> List[dict]:
    """
    Phase 1.5: Detailed Requirements Analysis (Reverse RAG).
    Extracts functional/non-functional requirements with search queries.
    """
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
            chunk_text = chunk_bytes.decode('utf-8', errors='ignore')

        activity.logger.info(f"Analyzing requirements in chunk ({len(chunk_text)} chars)...")
        
        system_prompt = """Ты — ведущий системный аналитик и эксперт по технической документации. Твоя задача — анализировать фрагменты Технического Задания (ТЗ) и извлекать из них ключевые требования, риски и ограничения.

Ты работаешь в архитектуре "Reverse RAG". Это значит, что для каждого найденного пункта ты должен предоставить не только анализ, но и специальный поисковый запрос (`search_query`), который позволит алгоритму найти точное место в исходном тексте.

### Твои инструкции:
1.  **Анализ:** Внимательно прочитай входящий фрагмент текста. Выдели:
    * Функциональные требования (что система должна делать).
    * Нефункциональные требования (SLA, безопасность, стек, нагрузка).
    * Риски и ограничения (бюджет, сроки, юридические аспекты).

2.  **Генерация Search Query (Самое важное):**
    * Для каждого пункта создай поле `search_query`.
    * Это должна быть **дословная или максимально близкая к тексту фраза** из исходника, подтверждающая твой анализ.
    * Цель этого запроса — найти соответствующий вектор в базе данных (cosine similarity) (используется BGE-M3).
    * Избегай общих слов. Ищи уникальные формулировки, цифры, названия технологий или специфические термины, упомянутые в тексте.

3.  **Формат ответа:**
    * Отвечай СТРОГО в формате JSON списка.
    """

        result: RequirementAnalysisResult = await llm.create_structured_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Проанализируй следующий фрагмент ТЗ и верни JSON согласно системной инструкции.\n\n=== НАЧАЛО ФРАГМЕНТА ===\n{chunk_text}\n=== КОНЕЦ ФРАГМЕНТА ==="}
            ],
            output_model=RequirementAnalysisResult,
            tool_name="analyze_requirements"
        )
        
        return [item.model_dump() for item in result.items if item is not None]

    except Exception as e:
        activity.logger.error(f"Requirements Analysis Failed: {e}")
        return []


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
async def analyze_project_activity(merged_data: dict, additional_notes: str = "") -> dict:
    """
    Phase 2: Analysis based on aggregated data.
    Populates requirement_issues, suggested_stages, suggested_roles, and estimates.
    """
    llm = LLMService()
    
    # START OPTIMIZATION: Filter context to avoid 50k+ char payloads
    condensed_data = {
        "project_essence": merged_data.get("project_essence", ""),
        "project_type": merged_data.get("project_type", ""),
        "business_goals": merged_data.get("business_goals", ""),
        "tech_stack": merged_data.get("tech_stack", []),
        "key_features": merged_data.get("key_features", {}), 
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
{f'''
Дополнительные указания заказчика (ОБЯЗАТЕЛЬНО учти при анализе):
{additional_notes}

ВАЖНО: Если ты добавляешь новые этапы, роли или требования на основе этих указаний (а НЕ из данных ТЗ),
то помечай их как "Требование менеджера" в поле source.''' if additional_notes else ''}

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
