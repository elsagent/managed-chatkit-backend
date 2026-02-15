# backend/app/routes/admin.py

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/admin", tags=["admin"])

# Env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# If you use a proxy/gateway, override this. Otherwise default OpenAI API base.
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

if not OPENAI_API_KEY:
    # Don’t crash import-time; health can still work, but Chatkit endpoints will error cleanly.
    pass


def _headers() -> Dict[str, str]:
    """
    Chatkit requires the OpenAI-Beta header, otherwise you'll get:
    invalid_beta: 'OpenAI-Beta: chatkit_beta=v1'
    """
    if not OPENAI_API_KEY:
        return {
            "Accept": "application/json",
            "OpenAI-Beta": "chatkit_beta=v1",
        }

    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Accept": "application/json",
        "OpenAI-Beta": "chatkit_beta=v1",
    }


async def _upstream_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{OPENAI_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers(), params=params or {})
            text = r.text
            # try JSON always
            try:
                data = r.json()
            except Exception:
                data = {"detail": text}

            if r.status_code >= 400:
                # Bubble up OpenAI error payloads nicely
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
    limit: int = Query(100, ge=1, le=100),
    after: Optional[str] = Query(None),
) -> Any:
    """
    Proxies to:
      GET /chatkit/threads?limit=...&after=...
    """
    params: Dict[str, Any] = {"limit": limit}
    if after:
        params["after"] = after

    return await _upstream_get("/chatkit/threads", params=params)


async def _list_threads_paginated(
    threads_limit: int,
    max_threads: int,
) -> List[Dict[str, Any]]:
    """
    Fetch up to max_threads total threads, paging using `after`.
    """
    out: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"limit": threads_limit}
        if after:
            params["after"] = after

        page = await _upstream_get("/chatkit/threads", params=params)

        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list) or len(data) == 0:
            break

        for t in data:
            if len(out) >= max_threads:
                return out
            if isinstance(t, dict):
                out.append(t)

        # paging
        has_more = bool(page.get("has_more")) if isinstance(page, dict) else False
        last_id = page.get("last_id") if isinstance(page, dict) else None
        if not has_more or not last_id:
            break

        after = last_id

    return out


async def _list_items_for_thread(
    thread_id: str,
    items_limit: int,
) -> List[Dict[str, Any]]:
    """
    Fetch up to items_limit items for a thread. (Paginates if needed.)
    OpenAI endpoint:
      GET /chatkit/threads/{thread_id}/items?limit=...&after=...
    """
    collected: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"limit": min(items_limit, 100)}
        if after:
            params["after"] = after

        page = await _upstream_get(f"/chatkit/threads/{thread_id}/items", params=params)

        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list) or len(data) == 0:
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
    """
    Exports all threads + their items.
    Uses Chatkit REST endpoints:
      GET /chatkit/threads
      GET /chatkit/threads/{thread_id}/items

    Optional:
      thread_id=... to export a single thread only.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail={"message": "OPENAI_API_KEY is not set"})

    # If they ask for a single thread, don’t paginate threads at all.
    if thread_id:
        # Fetch that thread's items
        items = await _list_items_for_thread(thread_id=thread_id, items_limit=items_limit)

        # Best-effort: find the thread metadata by searching first page(s)
        # (Chatkit doesn't always expose a "get thread by id" endpoint)
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
            })

    return exported
