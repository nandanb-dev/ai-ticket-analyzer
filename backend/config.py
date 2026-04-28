import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
JIRA_URL: str       = os.getenv("JIRA_URL", "")
JIRA_USERNAME: str  = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
