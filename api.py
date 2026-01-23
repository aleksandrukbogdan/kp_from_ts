# api.py
import asyncio
import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Cookie, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client

# Импорт твоих workflow
from workflows import ProposalWorkflow
from users import validate_user
from fastapi.responses import StreamingResponse
from utils_docx import markdown_to_docx

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
    user: str = Depends(verify_auth)
):
    client = await get_temporal_client()
    content = await file.read()
    
    # Уникальный ID для идемпотентности
    wf_id = f"cp-{file.filename}-{len(content)}"
    
    try:
        handle = await client.start_workflow(
            ProposalWorkflow.run,
            args=[content, file.filename],
            id=wf_id,
            task_queue="proposal-queue", # Важно: совпадает с worker.py
        )
        return {"workflow_id": handle.id}
    except Exception as e:
        # Если workflow уже запущен, возвращаем его ID
        if "Workflow execution already started" in str(e):
             return {"workflow_id": wf_id}
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{workflow_id}")
async def get_status(workflow_id: str, user: str = Depends(verify_auth)):
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    
    try:
        # Используем твой Query метод из workflows.py
        state = await handle.query(ProposalWorkflow.get_data)
        return state
    except Exception as e:
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
    
    await handle.signal(ProposalWorkflow.user_approve_signal, signal_data)
    return {"status": "Signal sent"}

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