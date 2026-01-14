from datetime import timedelta
from temporalio import workflow
from activities import (
    parse_file_activite,
    analyze_tz_activity,
    generate_proposal_activity,
    save_budget_stub
)

@workflow.defn
class ProposalWorkflow:
    def __init__(self):
        self.extracted_data = None
        self.final_proposal = None
        self.is_approved = None
        self.status = "PROCESSING"
    
    @workflow.query
    def get_data(self):
        return {
            "extracted_data":self.extracted_data,
            "status": self.status,
            "final_proposal": self.final_proposal
        }
    
    @workflow.signal
    def user_approve_signal(self, updated_data:dict, price: float):
        self.extracted_data = updated_data
        self.extracted_data["price"] = price #заглушка расчетного блока
        self.is_approved = True
        
    @workflow.run
    async def run(self, file_content: bytes, file_name: str):
        #сначала cpu парсинг
        text = await workflow.execute_activity(
            parse_file_activity,
            args=[file_content, file_name],
            task_queue="main_queue",
            start_to_close_timeout=timedelta(minutes=1)
        )
        #сканы
        if not text or len(text) < 50:
            text = await workflow.execute_activity(
                ocr_document_activity,
                args=[file_content],
                task_queue="gpu-queue",
                start_to_close_timeout=timedelta(minutes=5)
            )
        #анализ ТЗ
        self.extracted_data = await workflow.execute_activity(
            analyze_tz_activity,
            text,
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        self.status = "WAITING_FOR_HUMAN"

        await workflow.wait_condition(lambda: self.is_approved)

        self.status = "GENERATING"

        self.final_proposal = await workflow.execute_activity(
            generate_proposal_activity,
            args=[self.extracted_data, self.extracted_data['price']],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        await workflow.execute_activity(
            save_budget_stub,
            self.extracted_data,
            task_queue="main-queue",
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        self.status = "COMPLETED"
        return self.final_proposal
        
    
