from __future__ import annotations

import json
import os
import uuid
from typing import Any, Mapping

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

SESSION_COOKIE_NAME = "chatkit_session_id"
SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days

# ==========================
# APP INIT
# ==========================

app = FastAPI(title="ELS Chat Backend With Logging")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://elsagentck.vercel.app",
        "https://elsagentck-git-main-electronic-locksmith.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
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
    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        ssl="require"
    )


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
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": user_message,
            },
        )

    if not response.is_success:
        return JSONResponse(
            {"error": response.text},
            status_code=response.status_code
        )

    result = response.json()

    try:
        assistant_text = result["output"][0]["content"][0]["text"]
    except Exception:
        assistant_text = "Sorry, something went wrong."

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