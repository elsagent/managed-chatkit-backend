from __future__ import annotations

import os
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from chatkit import router as chatkit_router

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable not set")

app = FastAPI(title="ELS Agent Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all while debugging
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatkit_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/create-session")
async def create_session(payload: dict):
    workflow_id = payload.get("workflow", {}).get("id")

    if not workflow_id:
        return JSONResponse(
            {"error": "Missing workflow id"},
            status_code=400
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chatkit/sessions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "chatkit_beta=v1",
            },
            json={
                "workflow": {"id": workflow_id},
                "user": {
                    "id": "local-user-1"
                }
            },
        )

    if response.status_code != 200:
        return JSONResponse(
            {"error": response.text},
            status_code=500
        )

    data = response.json()

    return {
        "client_secret": data.get("client_secret")
    }
