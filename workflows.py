
from datetime import timedelta
import asyncio
from temporalio import workflow
from activities import (
    parse_file_activity,
    # analyze_tz_activity, # Deprecated
    estimate_hours_activity,
    generate_proposal_activity,
    save_budget_stub,
    ocr_document_activity,
    split_text_activity,
    extract_chunk_activity,
    merge_data_activity,
    analyze_project_activity
)

@workflow.defn
class ProposalWorkflow:
    def __init__(self):
        self.extracted_data = None
        self.final_proposal = None
        self.is_approved = None
        self.status = "PROCESSING"
        self.budget = None
        self.rates = None
        self.raw_text_preview = None  # Preview placeholder
        self.raw_text_length = 0  # Approx length
        self.suggested_hours = None  # AI Suggestions
        self.suggested_stages = None  # AI Suggestions
        self.suggested_roles = None  # AI Suggestions
    
    @workflow.query
    def get_data(self):
        return {
            "extracted_data": self.extracted_data,
            "status": self.status,
            "final_proposal": self.final_proposal,
            "raw_text_preview": self.raw_text_preview,
            "raw_text_length": self.raw_text_length,
            "suggested_hours": self.suggested_hours,
            "suggested_stages": self.suggested_stages,
            "suggested_roles": self.suggested_roles
        }
    
    @workflow.signal
    def user_approve_signal(self, payload: dict):
        self.extracted_data = payload.get("updated_data")
        self.budget = payload.get("budget")
        self.rates = payload.get("rates")
        self.is_approved = True
        
    @workflow.run
    async def run(self, file_path: str, file_name: str):
        # 1. Parsing (CPU/Docling) - Returns Path to MD file now
        md_file_path = await workflow.execute_activity(
            parse_file_activity,
            args=[file_path, file_name],
            task_queue="proposal-queue",
            start_to_close_timeout=timedelta(minutes=10) # Increased for larger files
        )
        
        # 2. OCR Fallback (if needed)
        if not md_file_path:
             workflow.logger.info(f"Parsing failed or empty. Trying OCR for {file_path}")
             md_file_path = await workflow.execute_activity(
                ocr_document_activity,
                args=[file_path],
                task_queue="gpu-queue",
                start_to_close_timeout=timedelta(minutes=10)
            )

        if not md_file_path:
             self.status = "ERROR: Failed to parse document"
             return "Extraction Failed"

        # Set placeholder preview
        self.raw_text_preview = f"File processed successfully. Path: {md_file_path}"
        
        # 3. Splitting Text - Returns list of ChunkDefs (dicts)
        chunks_defs = await workflow.execute_activity(
            split_text_activity,
            args=[md_file_path],
            task_queue="proposal-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        if not chunks_defs:
             self.status = "ERROR: No text content found"
             return "No Content"

        self.raw_text_length = len(chunks_defs) * 12000 # Approx
        
        # 4. Parallel Extraction (Map Phase) - BATCHED
        # User requested speedup but GPU is at 96% load.
        # BATCH_SIZE = 3 (Safe start)
        BATCH_SIZE = 3
        partial_results = []
        
        for i in range(0, len(chunks_defs), BATCH_SIZE):
            batch_chunks = chunks_defs[i : i + BATCH_SIZE]
            
            extract_futures = [
                workflow.execute_activity(
                    extract_chunk_activity,
                    args=[chunk_def],
                    task_queue="gpu-queue", # Processing on GPU/LLM worker
                    start_to_close_timeout=timedelta(minutes=60)
                )
                for chunk_def in batch_chunks
            ]
            
            # Wait for the current batch to finish before scheduling the next
            # Aggressive parallelism here could OOM the VRAM if batch size is too high
            batch_results = await asyncio.gather(*extract_futures)
            partial_results.extend(batch_results)
        
        # 5. Merge (Reduce Phase)
        merged_data_dict = await workflow.execute_activity(
            merge_data_activity,
            args=[partial_results],
            task_queue="proposal-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        # 6. Analysis (Phase 2 - using Aggregated Data)
        self.extracted_data = await workflow.execute_activity(
            analyze_project_activity,
            args=[merged_data_dict],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=10)
        )
        
        # 7. Post-Processing (Suggestions)
        self.suggested_stages = self.extracted_data.get(
            "suggested_stages", 
            ["Сбор данных", "Прототип", "Разработка", "Тестирование"]
        )
        self.suggested_roles = self.extracted_data.get(
            "suggested_roles",
            ["Менеджер", "Frontend", "Backend", "Дизайнер"]
        )
        
        # 8. Budget Estimation Matrix
        self.suggested_hours = await workflow.execute_activity(
            estimate_hours_activity,
            args=[self.extracted_data, self.suggested_stages, self.suggested_roles],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=10)
        )
        
        self.status = "WAITING_FOR_HUMAN"

        await workflow.wait_condition(lambda: self.is_approved)

        self.status = "GENERATING"

        self.final_proposal = await workflow.execute_activity(
            generate_proposal_activity,
            args=[self.extracted_data, self.budget, self.rates],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=10)
        )
        await workflow.execute_activity(
            save_budget_stub,
            args=[self.extracted_data],
            task_queue="proposal-queue",
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        self.status = "COMPLETED"
        return self.final_proposal
