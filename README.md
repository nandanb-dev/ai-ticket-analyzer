# ai-ticket-analyzer
AI tool that converts unclear Jira tickets into clear, testable, implementation-ready requirements with generated acceptance criteria and test scenarios.

## Prerequisites

- Python 3.10+
- pip
- Any AI API key (will need to make changes to remove existing openAI keys)
- (Optional) JIRA Cloud credentials, if you want to push generated tickets to JIRA

## Project structure

- `backend/` - FastAPI app and AI/JIRA integration
- `frontend/` - frontend placeholder (currently minimal)

## Backend setup

1. Move into the backend folder:

```bash
cd backend
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the app

From the `backend/` folder:

```bash
python run.py
```

Server URL:
- http://localhost:8000

API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Common issues

- `API_KEY is not configured in .env`
	- Ensure `.env` is in the `backend/` folder and includes `API_KEY=...`.

- `API key not valid` / `API_KEY_INVALID`
	- Create a new key in and paste it exactly.
	- Restart the server after updating `.env`.

- JIRA authentication errors
	- Verify `JIRA_URL`, `JIRA_USERNAME`, and `JIRA_API_TOKEN` values.
