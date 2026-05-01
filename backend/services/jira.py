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


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_issues_by_jql(jql: str, max_results: int = 200) -> list[dict]:
    """Execute a JQL query and return a flat list of simplified issue dicts."""
    if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
        raise HTTPException(status_code=500, detail="JIRA credentials not configured in .env")

    fields = "summary,description,issuetype,priority,labels,status,assignee,parent,subtasks,customfield_10016,customfield_10014,customfield_10028"
    start_at = 0
    all_issues: list[dict] = []

    while True:
        resp = requests.get(
            f"{JIRA_URL}/rest/api/3/search/jql",
            params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": min(50, max_results - len(all_issues)),
                "fields": fields,
            },
            auth=(JIRA_USERNAME, JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if not resp.ok:
            raise HTTPException(status_code=502, detail=f"JIRA search error: {resp.text}")

        data = resp.json()
        issues = data.get("issues", [])
        all_issues.extend(_simplify_issue(i) for i in issues)

        if len(all_issues) >= data.get("total", 0) or len(all_issues) >= max_results:
            break
        start_at += len(issues)

    return all_issues


def _simplify_issue(issue: dict) -> dict:
    """Extract the fields we care about into a flat dict."""
    fields = issue.get("fields", {})
    description_raw = fields.get("description") or {}
    description_text = _adf_to_text(description_raw) if isinstance(description_raw, dict) else (description_raw or "")

    parent = fields.get("parent") or {}
    assignee = fields.get("assignee") or {}

    # story_points is stored in customfield_10016 in most JIRA cloud instances
    story_points = (
        fields.get("story_points")
        or fields.get("customfield_10016")
        or fields.get("customfield_10028")
    )

    return {
        "key": issue["key"],
        "summary": fields.get("summary", ""),
        "description": description_text,
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "labels": fields.get("labels", []),
        "assignee": assignee.get("displayName", ""),
        "story_points": story_points,
        "parent_key": parent.get("key", ""),
        "parent_summary": parent.get("fields", {}).get("summary", "") if parent else "",
    }


def _adf_to_text(adf: dict) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if not adf:
        return ""
    parts: list[str] = []
    for node in adf.get("content", []):
        node_type = node.get("type", "")
        if node_type == "text":
            parts.append(node.get("text", ""))
        elif node_type in ("paragraph", "heading", "bulletList", "orderedList", "listItem", "blockquote", "codeBlock", "panel"):
            parts.append(_adf_to_text(node))
            if node_type in ("paragraph", "heading"):
                parts.append("\n")
        else:
            parts.append(_adf_to_text(node))
    return "".join(parts).strip()


def fetch_project_tickets(project_key: str) -> list[dict]:
    """Fetch all non-done tickets for a project, ordered by issue type."""
    jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY issuetype ASC, created ASC'
    return _fetch_issues_by_jql(jql)


def fetch_epic_tickets(epic_key: str) -> list[dict]:
    """Fetch an epic and all stories/tasks that belong to it."""
    # Fetch the epic itself
    resp = requests.get(
        f"{JIRA_URL}/rest/api/3/issue/{epic_key}",
        params={"fields": "summary,description,issuetype,priority,labels,status,customfield_10016"},
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"JIRA error fetching epic: {resp.text}")

    epic_issue = _simplify_issue(resp.json())
    children_jql = (
        f'"Epic Link" = {epic_key} OR parent = {epic_key} '
        f'ORDER BY issuetype ASC, created ASC'
    )
    try:
        children = _fetch_issues_by_jql(children_jql)
    except HTTPException as exc:
        # Team-managed projects can use parentEpic instead of Epic Link.
        if exc.status_code != 502:
            raise
        fallback_jql = (
            f'parentEpic = {epic_key} OR parent = {epic_key} '
            f'ORDER BY issuetype ASC, created ASC'
        )
        children = _fetch_issues_by_jql(fallback_jql)
    return [epic_issue] + children


def fetch_ticket_by_key(issue_key: str) -> list[dict]:
    """Fetch a single ticket by key and return it as a one-item list."""
    if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
        raise HTTPException(status_code=500, detail="JIRA credentials not configured in .env")

    resp = requests.get(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}",
        params={
            "fields": "summary,description,issuetype,priority,labels,status,assignee,parent,customfield_10016,customfield_10014,customfield_10028",
        },
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"JIRA error fetching issue {issue_key}: {resp.text}")
    return [_simplify_issue(resp.json())]


def _get_editable_fields(issue_key: str) -> set[str] | None:
    """Return editable field ids for this issue, or None if editmeta is unavailable."""
    resp = requests.get(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}/editmeta",
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        return None
    return set((resp.json().get("fields") or {}).keys())


def update_issue(issue_key: str, summary: str | None, description: str | None,
                 priority: str | None, labels: list[str] | None,
                 story_points: int | None, acceptance_criteria: list[dict] | None,
                 test_cases: list[dict] | None, edge_cases: list[str] | None) -> dict:
    """Apply a subset of field updates to an existing JIRA issue."""
    if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
        raise HTTPException(status_code=500, detail="JIRA credentials not configured in .env")

    editable_fields = _get_editable_fields(issue_key)
    warnings: list[str] = []

    def _is_editable(field_id: str) -> bool:
        return editable_fields is None or field_id in editable_fields

    fields: dict = {}
    if summary is not None:
        if _is_editable("summary"):
            fields["summary"] = summary[:255]
        else:
            warnings.append("summary not editable on this issue screen")
    if priority is not None:
        if _is_editable("priority"):
            fields["priority"] = {"name": priority}
        else:
            warnings.append("priority not editable on this issue screen")
    if labels is not None:
        if _is_editable("labels"):
            fields["labels"] = labels
        else:
            warnings.append("labels not editable on this issue screen")
    if story_points is not None:
        story_point_field_candidates = ["customfield_10016", "customfield_10014", "customfield_10028", "story_points"]
        story_point_field = next((f for f in story_point_field_candidates if _is_editable(f)), None)
        if story_point_field:
            fields[story_point_field] = story_points
        else:
            warnings.append("story points field is not editable/available; skipped")

    # Build an enriched description if any narrative parts are provided
    if description is not None or acceptance_criteria or test_cases or edge_cases:
        base = description or ""
        if acceptance_criteria:
            lines = "\n".join(
                f"- GIVEN {ac['given']} WHEN {ac['when']} THEN {ac['then']}"
                for ac in acceptance_criteria
            )
            base += f"\n\nAcceptance Criteria:\n{lines}"
        if test_cases:
            lines = "\n".join(
                f"- [{tc['type'].upper()}] {tc['title']}\n"
                f"  Steps: {' → '.join(tc.get('steps', []))}\n"
                f"  Expected: {tc.get('expected', '')}"
                for tc in test_cases
            )
            base += f"\n\nTest Cases:\n{lines}"
        if edge_cases:
            base += "\n\nEdge Cases:\n" + "\n".join(f"- {e}" for e in edge_cases)
        if _is_editable("description"):
            fields["description"] = _text_to_adf(base)
        else:
            warnings.append("description not editable on this issue screen")

    if not fields:
        return {"key": issue_key, "status": "no_changes", "warnings": warnings}

    resp = requests.put(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}",
        json={"fields": fields},
        auth=(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"JIRA update error for {issue_key}: {resp.text}")
    return {"key": issue_key, "status": "updated", "warnings": warnings}
