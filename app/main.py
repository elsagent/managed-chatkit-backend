from fastapi import FastAPI
from app.routes.admin import router as admin_router

app = FastAPI(title="ELS Agent Backend")

# Mount admin router under /admin (so /admin/health, /admin/chatkit/threads, /admin/chatkit/export)
app.include_router(admin_router)

# Also expose a root health endpoint for Render checks
@app.get("/health")
async def health():
    return {"status": "ok"}
