import requests
from fastapi import HTTPException

from config import JIRA_API_TOKEN, JIRA_URL, JIRA_USERNAME


def _text_to_adf(text: str) -> dict:
    """Convert plain text with newlines into a proper Atlassian Document Format (ADF) doc."""
    paragraphs = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Emit an empty paragraph for blank lines to preserve spacing
        content = [{"type": "text", "text": stripped}] if stripped else []
        paragraphs.append({"type": "paragraph", "content": content})
    if not paragraphs:
        paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    return {"type": "doc", "version": 1, "content": paragraphs}


def create_issue(
    project_key: str,
    issue_type: str,
    summary: str,
    description: str,
    priority: str,
    labels: list,
    parent_key: str = None,
) -> dict:
    fields = {
        "project":     {"key": project_key},
        "summary":     summary[:255],
        "description": _text_to_adf(description),
        "issuetype":   {"name": issue_type},
        "priority":    {"name": priority},
        "labels":      labels,
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}

    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/issue",
        json={"fields": fields},
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )

    # Some JIRA project types don't support cross-level parent linking.
    # Retry without the parent field so the ticket is still created.
    if not resp.ok and parent_key and "parentId" in resp.text:
        fields.pop("parent", None)
        resp = requests.post(
            f"{JIRA_URL}/rest/api/3/issue",
            json={"fields": fields},
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

    # Epics — created first so stories can link to them
    epic_keys = []
    for epic in epics:
        result = create_issue(
            project_key=project_key,
            issue_type="Epic",
            summary=epic["summary"],
            description=epic["description"],
            priority=epic.get("priority", "Medium"),
            labels=epic.get("labels", []),
        )
        epic_keys.append(result["key"])
        created["epics"].append({"key": result["key"], "summary": epic["summary"]})

    # Stories — linked to their parent epic via epic_index
    story_keys = []
    for story in stories:
        description = _build_story_description(story)
        epic_idx = story.get("epic_index", 0)
        parent_key = epic_keys[epic_idx] if epic_idx < len(epic_keys) else None

        result = create_issue(
            project_key=project_key,
            issue_type="Story",
            summary=story["summary"],
            description=description,
            priority=story.get("priority", "Medium"),
            labels=story.get("labels", []),
            parent_key=parent_key,
        )
        story_keys.append(result["key"])
        created["stories"].append({"key": result["key"], "summary": story["summary"]})

    # Tasks — linked to their parent story via story_index
    for task in tasks:
        description = _build_task_description(task)
        story_idx = task.get("story_index", 0)
        parent_key = story_keys[story_idx] if story_idx < len(story_keys) else None

        result = create_issue(
            project_key=project_key,
            issue_type="Task",
            summary=task["summary"],
            description=description,
            priority=task.get("priority", "Medium"),
            labels=task.get("labels", []),
            parent_key=parent_key,
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
            f"- [{tc['type'].upper()}] {tc['title']}\n"
            f"  Steps: {' → '.join(tc.get('steps', []))}\n"
            f"  Expected: {tc.get('expected', '')}"
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
