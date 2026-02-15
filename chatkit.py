from fastapi import APIRouter
from openai import OpenAI
import os

router = APIRouter()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@router.post("/api/chatkit")
async def chatkit():
    session = client.chatkit.sessions.create(
        workflow=os.environ["CHATKIT_WORKFLOW_ID"]
    )

    return {
        "client_secret": session.client_secret
    }
