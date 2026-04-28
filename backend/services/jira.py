import requests
from fastapi import HTTPException

from config import JIRA_API_TOKEN, JIRA_URL, JIRA_USERNAME


def create_issue(
    project_key: str,
    issue_type: str,
    summary: str,
    description: str,
    priority: str,
    labels: list,
) -> dict:
    payload = {
        "fields": {
            "project":     {"key": project_key},
            "summary":     summary[:255],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            },
            "issuetype": {"name": issue_type},
            "priority":  {"name": priority},
            "labels":    labels,
        }
    }

    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/issue",
        json=payload,
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"JIRA error: {resp.text}")
    return resp.json()


def push_tickets(project_key: str, ticket_data: dict) -> dict:
    epics   = ticket_data.get("epics", [])
    stories = ticket_data.get("stories", [])
    tasks   = ticket_data.get("tasks", [])

    created = {"epics": [], "stories": [], "tasks": []}

    # Epics
    for epic in epics:
        result = create_issue(
            project_key=project_key,
            issue_type="Epic",
            summary=epic["summary"],
            description=epic["description"],
            priority=epic.get("priority", "Medium"),
            labels=epic.get("labels", []),
        )
        created["epics"].append({"key": result["key"], "summary": epic["summary"]})

    # Stories
    for story in stories:
        description = _build_story_description(story)

        result = create_issue(
            project_key=project_key,
            issue_type="Story",
            summary=story["summary"],
            description=description,
            priority=story.get("priority", "Medium"),
            labels=story.get("labels", []),
        )
        created["stories"].append({"key": result["key"], "summary": story["summary"]})

    # Tasks
    for task in tasks:
        description = _build_task_description(task)

        result = create_issue(
            project_key=project_key,
            issue_type="Task",
            summary=task["summary"],
            description=description,
            priority=task.get("priority", "Medium"),
            labels=task.get("labels", []),
        )
        created["tasks"].append({"key": result["key"], "summary": task["summary"]})

    return created


def _build_story_description(story: dict) -> str:
    description = story["description"]

    if story.get("acceptance_criteria"):
        lines = "\n".join(
            f"- GIVEN {ac['given']} WHEN {ac['when']} THEN {ac['then']}"
            for ac in story["acceptance_criteria"]
        )
        description += f"\n\nAcceptance Criteria:\n{lines}"

    if story.get("test_cases"):
        lines = "\n".join(
            f"- [{tc['type'].upper()}] {tc['title']}: {' → '.join(tc.get('steps', []))}"
            for tc in story["test_cases"]
        )
        description += f"\n\nTest Cases:\n{lines}"

    if story.get("edge_cases"):
        description += "\n\nEdge Cases:\n" + "\n".join(f"- {e}" for e in story["edge_cases"])

    return description


def _build_task_description(task: dict) -> str:
    description = task["description"]

    if task.get("acceptance_criteria"):
        lines = "\n".join(
            f"- GIVEN {ac['given']} WHEN {ac['when']} THEN {ac['then']}"
            for ac in task["acceptance_criteria"]
        )
        description += f"\n\nAcceptance Criteria:\n{lines}"

    return description
