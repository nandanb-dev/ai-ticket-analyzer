from fastapi import FastAPI

from routes.tickets import router

app = FastAPI(
    title="AI Ticket Analyzer",
    description="Upload a PRD → get JIRA tickets with acceptance criteria & test cases",
    version="1.0.0",
)

app.include_router(router)

