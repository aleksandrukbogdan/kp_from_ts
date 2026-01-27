from datetime import timedelta
from temporalio import workflow
from activities import (
    parse_file_activity,
    analyze_tz_activity,
    estimate_hours_activity,
    generate_proposal_activity,
    save_budget_stub,
    ocr_document_activity
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
        self.raw_text = None  # Исходный текст ТЗ
        self.suggested_hours = None  # Предложенные часы от ИИ
        self.suggested_stages = None  # Рекомендуемые этапы от ИИ
        self.suggested_roles = None  # Рекомендуемые роли от ИИ
    
    @workflow.query
    def get_data(self):
        return {
            "extracted_data": self.extracted_data,
            "status": self.status,
            "final_proposal": self.final_proposal,
            "raw_text": self.raw_text,
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
    async def run(self, file_content: bytes, file_name: str):
        #сначала cpu парсинг
        text = await workflow.execute_activity(
            parse_file_activity,
            args=[file_content, file_name],
            task_queue="proposal-queue",
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
        self.raw_text = text  # Сохраняем для отображения в UI
        self.extracted_data = await workflow.execute_activity(
            analyze_tz_activity,
            args=[text],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        # Берём этапы и роли от ИИ (или дефолтные)
        self.suggested_stages = self.extracted_data.get(
            "suggested_stages", 
            ["Сбор данных", "Прототип", "Разработка", "Тестирование"]
        )
        self.suggested_roles = self.extracted_data.get(
            "suggested_roles",
            ["Менеджер", "Frontend", "Backend", "Дизайнер"]
        )
        
        # Оценка трудозатрат (подсказки для матрицы)
        self.suggested_hours = await workflow.execute_activity(
            estimate_hours_activity,
            args=[self.extracted_data, self.suggested_stages, self.suggested_roles],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=1)
        )
        
        self.status = "WAITING_FOR_HUMAN"

        await workflow.wait_condition(lambda: self.is_approved)

        self.status = "GENERATING"

        self.final_proposal = await workflow.execute_activity(
            generate_proposal_activity,
            args=[self.extracted_data, self.budget, self.rates],
            task_queue="gpu-queue",
            start_to_close_timeout=timedelta(minutes=2)
        )
        await workflow.execute_activity(
            save_budget_stub,
            self.extracted_data,
            task_queue="proposal-queue",
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        self.status = "COMPLETED"
        return self.final_proposal
        
    
