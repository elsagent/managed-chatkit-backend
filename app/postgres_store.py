from __future__ import annotations

import json
import asyncpg
from chatkit.store import NotFoundError, Store
from chatkit.types import Attachment, Page, ThreadItem, ThreadMetadata


class PostgresStore(Store[dict]):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, database_url: str) -> "PostgresStore":
        pool = await asyncpg.create_pool(dsn=database_url)
        return cls(pool)

    async def load_thread(self, thread_id: str, context: dict) -> ThreadMetadata:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, created_at, title, metadata FROM chat_threads WHERE id=$1",
                thread_id,
            )
            if not row:
                raise NotFoundError(f"Thread {thread_id} not found")

            return ThreadMetadata(
                id=row["id"],
                created_at=row["created_at"],
                title=row["title"],
                metadata=row["metadata"] or {},
            )

    async def save_thread(self, thread: ThreadMetadata, context: dict) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_threads (id, created_at, title, metadata)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (id) DO UPDATE
                SET title=EXCLUDED.title,
                    metadata=EXCLUDED.metadata
                """,
                thread.id,
                thread.created_at,
                thread.title,
                json.dumps(thread.metadata or {}),
            )

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem, context: dict
    ) -> None:
        await self.save_item(thread_id, item, context)

    async def save_item(
        self, thread_id: str, item: ThreadItem, context: dict
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_thread_items
                (id, thread_id, created_at, role, content, raw)
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (id) DO UPDATE
                SET role=EXCLUDED.role,
                    content=EXCLUDED.content,
                    raw=EXCLUDED.raw
                """,
                item.id,
                thread_id,
                item.created_at,
                item.role,
                json.dumps(item.content or {}),
                json.dumps(item.model_dump()),
            )

    async def load_thread_items(
        self, thread_id: str, after: str | None, limit: int, order: str, context: dict
    ) -> Page[ThreadItem]:
        direction = "DESC" if order == "desc" else "ASC"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, created_at, role, content, raw
                FROM chat_thread_items
                WHERE thread_id=$1
                ORDER BY created_at {direction}
                LIMIT $2
                """,
                thread_id,
                limit,
            )

        items = [
            ThreadItem(**(row["raw"] or {}))
            for row in rows
        ]

        return Page(data=items, has_more=False, after=None)

    async def load_threads(
        self, limit: int, after: str | None, order: str, context: dict
    ) -> Page[ThreadMetadata]:
        direction = "DESC" if order == "desc" else "ASC"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, created_at, title, metadata
                FROM chat_threads
                ORDER BY created_at {direction}
                LIMIT $1
                """,
                limit,
            )

        threads = [
            ThreadMetadata(
                id=row["id"],
                created_at=row["created_at"],
                title=row["title"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]

        return Page(data=threads, has_more=False, after=None)

    async def delete_thread(self, thread_id: str, context: dict) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM chat_threads WHERE id=$1",
                thread_id,
            )

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: dict
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM chat_thread_items WHERE id=$1",
                item_id,
            )

    async def save_attachment(self, attachment: Attachment, context: dict) -> None:
        raise NotImplementedError()

    async def load_attachment(self, attachment_id: str, context: dict) -> Attachment:
        raise NotImplementedError()

    async def delete_attachment(self, attachment_id: str, context: dict) -> None:
        raise NotImplementedError()
