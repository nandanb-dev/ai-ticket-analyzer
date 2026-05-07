import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
JIRA_URL: str       = os.getenv("JIRA_URL", "")
JIRA_USERNAME: str  = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
CHAT_MODEL: str     = os.getenv("CHAT_MODEL", "gpt-4o")
CONFLUENCE_URL: str       = os.getenv("CONFLUENCE_URL", "")
CONFLUENCE_USERNAME: str  = os.getenv("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN", "")

CORS_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
