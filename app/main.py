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

# 🔴 TEMPORARY: Hardcoded DB for debugging
# We remove dotenv completely to avoid parsing errors
DATABASE_URL = "postgresql://neondb_owner:npg_lzpv6frtk7eV@ep-bitter-frog-ai5ww9ae-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

DEFAULT_CHATKIT_BASE = "https://api.openai.com"
SESSION_COOKIE_NAME = "chatkit_session_id"
SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days

# ==========================
# APP INIT
# ==========================

app = FastAPI(title="ELS Chat Backend With Logging")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all during development
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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JSONResponse({"error": "Missing OPENAI_API_KEY"}, status_code=500)

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
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": user_message,
            },
        )

    result = response.json()

    assistant_text = result["output"][0]["content"][0]["text"]

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