# backend/app/routes/admin.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/admin", tags=["admin"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def _headers() -> Dict[str, str]:
    # Chatkit requires this beta header
    h: Dict[str, str] = {
        "Accept": "application/json",
        "OpenAI-Beta": "chatkit_beta=v1",
    }
    if OPENAI_API_KEY:
        h["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    return h


async def _upstream_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{OPENAI_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers(), params=params or {})
            try:
                data = r.json()
            except Exception:
                data = {"detail": r.text}

            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=data)

            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": str(e)})


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@router.get("/chatkit/threads")
async def list_chatkit_threads(
    limit: int = Query(25, ge=1, le=100),
    after: Optional[str] = Query(None),
) -> Any:
    params: Dict[str, Any] = {"limit": limit}
    if after:
        params["after"] = after
    return await _upstream_get("/chatkit/threads", params=params)


async def _list_threads_paginated(threads_limit: int, max_threads: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"limit": threads_limit}
        if after:
            params["after"] = after

        page = await _upstream_get("/chatkit/threads", params=params)

        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list) or not data:
            break

        for t in data:
            if len(out) >= max_threads:
                return out
            if isinstance(t, dict):
                out.append(t)

        has_more = bool(page.get("has_more")) if isinstance(page, dict) else False
        last_id = page.get("last_id") if isinstance(page, dict) else None
        if not has_more or not last_id:
            break

        after = last_id

    return out


async def _list_items_for_thread(thread_id: str, items_limit: int) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"limit": min(items_limit, 100)}
        if after:
            params["after"] = after

        page = await _upstream_get(f"/chatkit/threads/{thread_id}/items", params=params)

        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list) or not data:
            break

        for it in data:
            if len(collected) >= items_limit:
                return collected
            if isinstance(it, dict):
                collected.append(it)

        has_more = bool(page.get("has_more")) if isinstance(page, dict) else False
        last_id = page.get("last_id") if isinstance(page, dict) else None
        if not has_more or not last_id:
            break

        after = last_id

    return collected


@router.get("/chatkit/export")
async def export_chatkit(
    threads_limit: int = Query(100, ge=1, le=100),
    items_limit: int = Query(100, ge=1, le=100),
    max_threads: int = Query(5000, ge=1, le=50000),
    thread_id: Optional[str] = Query(None),
) -> Any:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail={"message": "OPENAI_API_KEY is not set"})

    if thread_id:
        items = await _list_items_for_thread(thread_id=thread_id, items_limit=items_limit)
        threads = await _list_threads_paginated(threads_limit=threads_limit, max_threads=max_threads)
        tmeta = next((t for t in threads if t.get("id") == thread_id), {"id": thread_id})
        return [{
            "thread_id": tmeta.get("id"),
            "title": tmeta.get("title"),
            "user": tmeta.get("user"),
            "created_at": tmeta.get("created_at"),
            "items": items,
        }]

    threads = await _list_threads_paginated(threads_limit=threads_limit, max_threads=max_threads)

    exported: List[Dict[str, Any]] = []
    for t in threads:
        tid = t.get("id")
        if not tid:
            continue

        try:
            items = await _list_items_for_thread(thread_id=tid, items_limit=items_limit)
            exported.append({
                "thread_id": tid,
                "title": t.get("title"),
                "user": t.get("user"),
                "created_at": t.get("created_at"),
                "items": items,
            })
        except HTTPException as e:
            exported.append({
                "thread_id": tid,
                "title": t.get("title"),
                "user": t.get("user"),
                "created_at": t.get("created_at"),
                "error": e.detail,
                "status_code": e.status_code,
                "items": [],
            })

    return exported
