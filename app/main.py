# backend/app/main.py

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.routes.admin import router as admin_router

app = FastAPI(title="ELS Agent Backend")

# router already has prefix="/admin"
app.include_router(admin_router)

# Optional: root health (helps Render health checks)
@app.get("/health")
async def health():
    return {"status": "ok"}
