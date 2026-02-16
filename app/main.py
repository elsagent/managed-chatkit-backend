kfrom dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.routes.admin import router as admin_router

app = FastAPI(title="ELS Agent Backend")

app.include_router(admin_router)
