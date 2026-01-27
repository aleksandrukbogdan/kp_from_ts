import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from activities import (
    parse_file_activity,
    analyze_tz_activity,
    estimate_hours_activity,
    generate_proposal_activity,
    save_budget_stub,
    ocr_document_activity
)
from workflows import ProposalWorkflow

async def main():
    client = await Client.connect("temporal-server:7233") #подключение к темпорал серверу
#добавить 2 воркера: 1 для обычной очереди другой для gpu
    worker_cpu = Worker(
        client,
        task_queue="proposal-queue",
        workflows=[ProposalWorkflow],
        activities=[parse_file_activity, save_budget_stub]
    )
    
    worker_gpu = Worker(
        client,
        task_queue="gpu-queue",
        # workflow тут не нужен, только активности
        activities=[ocr_document_activity, analyze_tz_activity, estimate_hours_activity, generate_proposal_activity]
    )
    print("Workers started")
    await asyncio.gather(worker_cpu.run(), worker_gpu.run())

if __name__ == "__main__":
    asyncio.run(main())