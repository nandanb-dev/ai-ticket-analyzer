from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ALLOWED_ORIGINS
from routes.analyze import router as analyze_router
from routes.chat import router as chat_router
from routes.tickets import router as tickets_router

app = FastAPI(
    title="AI Ticket Analyzer",
    description="Chat with your product context, preview tickets, and confirm before JIRA creation",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(tickets_router)
app.include_router(analyze_router)

