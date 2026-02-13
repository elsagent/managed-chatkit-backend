from __future__ import annotations

import os
import json
import uuid
from typing import Any

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ==========================
# CONFIGURATION
# ==========================

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable not set")

DEFAULT_CHATKIT_BASE = "https://api.openai.com"

# ==========================
# APP INIT
# ==========================

app = FastAPI(title="ELS Chat Backend With Logging")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://elsagent.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool: asyncpg.Pool | None = None

# ==========================
# STARTUP / SHUTDOWN
# ==========================

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL)


@app.on_event("shutdown")
async def shutdown():
    global pool
    if pool:
        await pool.close()


# ==========================
# HEALTH CHECK
# ==========================

@app.get("/health")
async def health():
    return {"status": "ok"}


# ==========================
# CREATE SESSION (ChatKit)
# ==========================

@app.post("/api/create-session")
async def create_session(request: Request):
    body = await request.json()
    workflow = body.get("workflow")

    if not workflow or not workflow.get("id"):
        return JSONResponse({"error": "Missing workflow id"}, status_code=400)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DEFAULT_CHATKIT_BASE}/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": "Session initialized.",
            },
        )

    if response.status_code != 200:
        return JSONResponse(
            {"error": "Failed to create OpenAI session"},
            status_code=500,
        )

    # For ChatKit, we return a temporary client secret.
    # In production you would call the proper ChatKit session endpoint.
    return {
        "client_secret": OPENAI_API_KEY
    }


# ==========================
# CHAT ENDPOINT WITH LOGGING
# ==========================

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body.get("message")
    thread_id = body.get("thread_id")

    if not user_message:
        return JSONResponse({"error": "Missing message"}, status_code=400)

    if not thread_id:
        thread_id = str(uuid.uuid4())

    # Save user message
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_threads (id, created_at, metadata)
            VALUES ($1, NOW(), '{}'::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            thread_id,
        )

        await conn.execute(
            """
            INSERT INTO chat_thread_items
            (id, thread_id, created_at, role, content, raw)
            VALUES ($1, $2, NOW(), $3, $4, $5)
            """,
            str(uuid.uuid4()),
            thread_id,
            "user",
            json.dumps({"text": user_message}),
            json.dumps({"text": user_message}),
        )

    # Call OpenAI
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DEFAULT_CHATKIT_BASE}/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": user_message,
            },
        )

    if response.status_code != 200:
        return JSONResponse(
            {"error": "OpenAI request failed"},
            status_code=500,
        )

    result = response.json()

    try:
        assistant_text = result["output"][0]["content"][0]["text"]
    except Exception:
        return JSONResponse(
            {"error": "Unexpected OpenAI response format"},
            status_code=500,
        )

    # Save assistant message
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_thread_items
            (id, thread_id, created_at, role, content, raw)
            VALUES ($1, $2, NOW(), $3, $4, $5)
            """,
            str(uuid.uuid4()),
            thread_id,
            "assistant",
            json.dumps({"text": assistant_text}),
            json.dumps(result),
        )

    return {
        "thread_id": thread_id,
        "reply": assistant_text,
    }
