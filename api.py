# api.py
import asyncio
import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Cookie, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client

# Импорт твоих workflow
from workflows import ProposalWorkflow
from users import validate_user
from database import (
    save_user_file, 
    update_file_status,
    get_user_files,
    get_file_by_workflow_id,
    get_file_owner
)
from fastapi.responses import StreamingResponse
from utils_docx import markdown_to_docx
import shutil
import uuid

SHARED_DIR = "/shared_data"
os.makedirs(SHARED_DIR, exist_ok=True)

app = FastAPI(title="Agent KP API")

# Динамически определяем адрес сервера
IS_DEV = os.getenv('IS_DEV', 'false').lower() == 'true'
SERVER_ADDRESS = 'localhost' if IS_DEV else '10.109.50.250'

# CORS: Разрешаем React обращаться к API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{SERVER_ADDRESS}:5173",
        "http://localhost:5173",  # Всегда разрешаем localhost для удобства отладки
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Зависимости ---

async def get_temporal_client():
    return await Client.connect("temporal-server:7233")

async def verify_auth(request: Request):
    """
    Проверяет наличие куки авторизации от portal_app.py.
    В продакшене здесь стоит добавить валидацию токена через Redis или БД.
    """
    token = request.cookies.get("portal_auth_token")
    user = request.cookies.get("portal_user")
    if not token or not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# --- Модели данных (Pydantic) ---

class ApprovalRequest(BaseModel):
    updated_data: Dict[str, Any]
    budget: Dict[str, Dict[str, float]] # Структура {Stage: {Role: hours}}
    rates: Dict[str, float]

class LoginRequest(BaseModel):
    username: str
    password: str

# --- Endpoints ---

class DownloadRequest(BaseModel):
    text: str

@app.post("/api/login")
async def login(request: LoginRequest):
    """Аутентификация пользователя"""
    if validate_user(request.username, request.password):
        # Генерируем простой токен (в продакшене используй JWT)
        import hashlib
        import time
        token = hashlib.sha256(f"{request.username}{time.time()}".encode()).hexdigest()[:32]
        return {"success": True, "token": token}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/start")
async def start_workflow(
    file: UploadFile = File(...),
    convert_to_pdf_for_pages: bool = Form(default=True),  # Convert DOCX→PDF for page numbers
    user: str = Depends(verify_auth)
):
    client = await get_temporal_client()
    
    # Genererate ID and Path
    unique_id = str(uuid.uuid4())
    safe_filename = file.filename.replace(" ", "_").replace("/", "")
    file_path = os.path.join(SHARED_DIR, f"{unique_id}_{safe_filename}")
    
    # Stream save to disk (Memory efficient)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    
    wf_id = f"cp-{unique_id}"
    
    try:
        handle = await client.start_workflow(
            ProposalWorkflow.run,
            args=[file_path, file.filename, convert_to_pdf_for_pages],  # Pass conversion flag
            id=wf_id,
            task_queue="proposal-queue", # Важно: совпадает с worker.py
        )
        
        # Save to user history database
        save_user_file(
            username=user,
            workflow_id=handle.id,
            original_filename=file.filename
        )
        
        return {"workflow_id": handle.id}
    except Exception as e:
        # Если workflow уже запущен, возвращаем его ID
        if "Workflow execution already started" in str(e):
             return {"workflow_id": wf_id}
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history(user: str = Depends(verify_auth)):
    """Get file upload history for the current user with live status sync."""
    from datetime import timedelta
    
    files = get_user_files(user)
    client = await get_temporal_client()
    
    # For non-completed workflows, try to sync status from Temporal
    for f in files:
        if f.get('status') not in ('COMPLETED', None):
            try:
                handle = client.get_workflow_handle(f['workflow_id'])
                state = await handle.query(ProposalWorkflow.get_data, rpc_timeout=timedelta(seconds=2))
                new_status = state.get('status', 'PROCESSING')
                
                # Update cache if status changed
                if new_status != f.get('status'):
                    state_to_cache = {k: v for k, v in state.items() if k != 'final_proposal'}
                    update_file_status(
                        workflow_id=f['workflow_id'],
                        status=new_status,
                        extracted_data=state_to_cache,
                        final_proposal=state.get('final_proposal')
                    )
                    f['status'] = new_status
            except Exception as e:
                # On error, keep existing status (workflow might be completed or not found)
                error_msg = str(e).lower()
                if 'workflow execution already completed' in error_msg:
                    # Mark as completed in DB
                    update_file_status(workflow_id=f['workflow_id'], status='COMPLETED')
                    f['status'] = 'COMPLETED'
    
    return {"files": files}


@app.get("/api/file/{workflow_id}")
async def get_file_details(workflow_id: str, user: str = Depends(verify_auth)):
    """Get details of a specific file by workflow_id, syncing from Temporal if cache empty."""
    from datetime import timedelta
    
    file_data = get_file_by_workflow_id(workflow_id)
    
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Security: only owner can access
    if file_data.get("username") != user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # If cache is empty, try to fetch from Temporal
    if not file_data.get('extracted_data') or not file_data.get('final_proposal'):
        try:
            client = await get_temporal_client()
            handle = client.get_workflow_handle(workflow_id)
            state = await handle.query(ProposalWorkflow.get_data, rpc_timeout=timedelta(seconds=5))
            
            # Update cache with fresh data
            state_to_cache = {k: v for k, v in state.items() if k != 'final_proposal'}
            update_file_status(
                workflow_id=workflow_id,
                status=state.get('status', file_data.get('status')),
                extracted_data=state_to_cache,
                final_proposal=state.get('final_proposal')
            )
            
            # Update response with fresh data
            file_data['extracted_data'] = state_to_cache
            file_data['final_proposal'] = state.get('final_proposal')
            file_data['status'] = state.get('status')
        except Exception as e:
            print(f"Failed to sync from Temporal for {workflow_id}: {e}")
            # Continue with cached data (might be partial)
    
    return file_data


@app.get("/api/status/{workflow_id}")
async def get_status(workflow_id: str, user: str = Depends(verify_auth)):
    from datetime import timedelta
    
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    
    try:
        # Query с коротким timeout - если worker занят, вернём статус "обработка"
        state = await handle.query(ProposalWorkflow.get_data, rpc_timeout=timedelta(seconds=10))
        
        # Sync status to database for history tracking
        # Cache the full state (excluding final_proposal which is cached separately)
        state_to_cache = {k: v for k, v in state.items() if k != 'final_proposal'}
        update_file_status(
            workflow_id=workflow_id,
            status=state.get("status", "PROCESSING"),
            extracted_data=state_to_cache,  # Full state for analysis restoration
            final_proposal=state.get("final_proposal")
        )
        
        return state
    except Exception as e:
        error_msg = str(e).lower()
        print(f"Query error for {workflow_id}: {type(e).__name__}: {e}")
        
        # Query timeout = worker занят LLM-активностью, workflow всё ещё работает
        if "timed out" in error_msg or "timeout" in error_msg:
            print(f"Query timeout for {workflow_id} - worker busy, returning PROCESSING status")
            return {
                "status": "PROCESSING",
                "extracted_data": None,
                "final_proposal": None,
                "raw_text_preview": None,
                "message": "Worker is processing LLM request, please wait..."
            }
        
        # Проверяем, существует ли workflow вообще
        try:
            await handle.describe()
            # Workflow существует, но query не удался - возвращаем статус обработки
            return {
                "status": "PROCESSING",
                "extracted_data": None,
                "final_proposal": None
            }
        except Exception:
            print(f"Workflow not found: {workflow_id}")
            raise HTTPException(status_code=404, detail="Workflow not found")

@app.post("/api/approve/{workflow_id}")
async def approve_workflow(
    workflow_id: str, 
    payload: ApprovalRequest,
    user: str = Depends(verify_auth)
):
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    
    # Формируем структуру сигнала, которую ждет workflows.py
    signal_data = {
        "updated_data": payload.updated_data,
        "budget": payload.budget,
        "rates": payload.rates
    }
    
    try:
        await handle.signal(ProposalWorkflow.user_approve_signal, signal_data)
        return {"status": "Signal sent"}
    except Exception as e:
        error_msg = str(e).lower()
        # If workflow is already completed, it cannot accept signals
        if "workflow execution already completed" in error_msg or "not found" in error_msg:
            raise HTTPException(
                status_code=409,  # Conflict
                detail="Этот документ уже завершён и не может быть повторно обработан. Загрузите файл заново для создания нового КП."
            )
        raise HTTPException(status_code=500, detail=f"Failed to send signal: {e}")

@app.post("/api/download_docx")
async def download_docx(request: DownloadRequest, user: str = Depends(verify_auth)):
    buffer = markdown_to_docx(request.text)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=Commercial_Proposal.docx"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)