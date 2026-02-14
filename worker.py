import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from activities import (
    parse_file_activity,
    estimate_hours_activity,
    generate_proposal_activity,
    save_budget_stub,
    ocr_document_activity,
    index_document_activity, # Replaced split_text
    extract_chunk_activity,
    merge_data_activity,
    analyze_project_activity,
    analyze_requirements_chunk_activity, # New
    refine_requirements_activity, # New
    enrich_with_rag_activity, # RAG enrichment
    classify_manager_notes_activity, # Manager notes classification
    deduplicate_data_activity # Deduplication & Summarization
)
from workflows import ProposalWorkflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions, SandboxMatcher

async def main():
    client = await Client.connect("temporal-server:7233") #подключение к темпорал серверу
    #добавить 2 воркера: 1 для обычной очереди другой для gpu
    worker_cpu = Worker(
        client,
        task_queue="proposal-queue",
        workflows=[ProposalWorkflow],
        activities=[
            parse_file_activity, 
            save_budget_stub, 
            index_document_activity, # Replaced split_text
            merge_data_activity
        ],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions(
                invalid_modules=SandboxMatcher(),
                invalid_module_members=SandboxMatcher(),
                passthrough_modules={
                    "numpy",
                    "torch",
                    "sentence_transformers",
                    "google",
                    "tensorflow",
                    "huggingface_hub",
                    "rag_service",
                    "activities",
                    "logging",
                    "dateutil",
                }
            )
        )
    )
    
    worker_gpu = Worker(
        client,
        task_queue="gpu-queue",
        max_concurrent_activities=5,
        # workflow тут не нужен, только активности
        activities=[
            ocr_document_activity, 
            estimate_hours_activity, 
            generate_proposal_activity,
            extract_chunk_activity,
            analyze_project_activity,
            analyze_requirements_chunk_activity, # New (LLM)
            refine_requirements_activity, # New (Embeddings/Search)
            enrich_with_rag_activity, # RAG enrichment
            classify_manager_notes_activity, # Manager notes
            deduplicate_data_activity # Deduplication & Summarization
        ]
    )
    print("Workers started")
    await asyncio.gather(worker_cpu.run(), worker_gpu.run())

if __name__ == "__main__":
    asyncio.run(main())