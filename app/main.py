from __future__ import annotations

import os
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ==========================
# CONFIG
# ==========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable not set")

# ==========================
# APP INIT
# ==========================

app = FastAPI(title="ELS Chat Backend")

# 🔥 IMPORTANT: CORS for your Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://elsagent.vercel.app"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ==========================
# HEALTH CHECK
# ==========================

@app.get("/health")
async def health():
    return {"status": "ok"}

# ==========================
# CHAT ENDPOINT
# ==========================

@app.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        user_message = body.get("message")

        if not user_message:
            return JSONResponse(
                {"error": "Missing message"},
                status_code=400
            )

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

        if response.status_code != 200:
            return JSONResponse(
                {"error": "OpenAI request failed"},
                status_code=500
            )

        result = response.json()

        assistant_text = (
            result.get("output", [{}])[0]
            .get("content", [{}])[0]
            .get("text", "No response")
        )

        return {
            "reply": assistant_text
        }

    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )
