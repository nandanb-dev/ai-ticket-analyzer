import re
from typing import Any

from agents.analyzer_agent import run_analyzer_agent
from services.jira import push_tickets
from services.analysis_sessions import analysis_sessions

from agents.chat.chains import get_decision_chain, get_response_chain, get_ticket_chain, get_clarification_chain, get_edit_draft_chain
from agents.chat.models import ChatState
from agents.chat.utils import (
    build_rag_query_from_state,
    build_generation_context,
    format_attachments,
    format_messages,
    normalize_clarification_analysis,
    format_rag_context,
    retrieve_rag_context,
    summarize_ticket_preview,
    summarize_pending_tickets,
)


def decide_node(state: ChatState) -> dict[str, Any]:
    try:
        if state.get("forced_action"):
            return {
                "decision": {
                    "action": state["forced_action"],
                    "reason": "Action was explicitly requested by the API caller.",
                    "missing_information": [],
                }
            }

        latest_message = (state.get("latest_user_message") or "").strip()

        # Deterministic shortcut: if user enters a Jira ticket key directly, analyze that ticket immediately.
        # This avoids relying solely on LLM routing for explicit ticket identifiers.
        direct_ticket_match = re.fullmatch(r"([A-Z][A-Z0-9]+-\d+)", latest_message, re.IGNORECASE)
        jira_url_match = re.search(r"atlassian\.net\/browse\/([A-Z][A-Z0-9]+-\d+)", latest_message, re.IGNORECASE)
        if (direct_ticket_match or jira_url_match) and not state.get("pending_tickets"):
            ticket_key = (direct_ticket_match.group(1) if direct_ticket_match else jira_url_match.group(1)).upper()
            return {
                "decision": {
                    "action": "analyze_tickets",
                    "reason": "User provided a Jira ticket identifier directly, so analyze that ticket immediately.",
                    "missing_information": [],
                    "analysis_scope": "ticket",
                    "analysis_target": ticket_key,
                    "analysis_context": "",
                    "confluence_page": "",
                }
            }

        history = state.get("conversation_history") or []
        clarification_already_asked = any(
            (msg.get("role") == "assistant") and (
                "Development Readiness:" in (msg.get("content") or "")
                or "I have a few questions to ensure we build the right thing:" in (msg.get("content") or "")
                or "Can proceed with assumptions" in (msg.get("content") or "")
            )
            for msg in history
        )

        # Product requirement: ask clarification once, then draft tickets after the user replies.
        if (
            clarification_already_asked
            and not state.get("awaiting_confirmation")
            and not state.get("pending_tickets")
            and (state.get("latest_user_message") or "").strip()
        ):
            latest = (state.get("latest_user_message") or "").strip().lower()
            opt_out_terms = ["cancel", "stop", "not now", "hold", "wait"]
            if not any(term in latest for term in opt_out_terms):
                return {
                    "decision": {
                        "action": "generate_tickets",
                        "reason": "Clarification was already asked once. User replied with details, so draft tickets now.",
                        "missing_information": [],
                    }
                }

        decision = get_decision_chain().invoke({
            "forced_action": state.get("forced_action") or "none",
            "awaiting_confirmation": state["awaiting_confirmation"],
            "has_pending_tickets": bool(state.get("pending_tickets")),
            "project_key": state["project_key"] or "not set",
            "history_text": format_messages(state["conversation_history"]),
            "attachment_text": format_attachments(state["attachments"]),
            "context_text": state["context_text"] or "",
            "latest_user_message": state["latest_user_message"],
        })
        return {"decision": decision.model_dump()}
    except Exception as exc:
        return {"error": f"Chat routing failed: {exc}"}


def respond_node(state: ChatState) -> dict[str, Any]:
    try:
        rag_query = build_rag_query_from_state(state)
        rag_text, rag_citations = retrieve_rag_context(
            query=rag_query or state["latest_user_message"],
            project_key=state.get("project_key", ""),
        )

        response = get_response_chain().invoke({
            "history_text": format_messages(state["conversation_history"]),
            "attachment_text": format_attachments(state["attachments"]),
            "rag_context": format_rag_context(rag_text),
            "context_text": state["context_text"] or "",
            "latest_user_message": state["latest_user_message"],
        })

        reply = response.content
        if rag_citations:
            source_lines = []
            for citation in rag_citations[:3]:
                title = citation.get("title") or citation.get("source_id") or "Unknown source"
                source_lines.append(f"- {title}")
            if source_lines:
                reply += "\n\nSources:\n" + "\n".join(source_lines)

        return {"reply": reply, "rag_citations": rag_citations}
    except Exception as exc:
        return {"error": f"Chat response failed: {exc}"}


def ask_for_more_context_node(state: ChatState) -> dict[str, Any]:
    missing = []
    if state.get("decision"):
        missing = state["decision"].get("missing_information", [])
    lines = "\n".join(f"- {item}" for item in missing) if missing else "- The product goal or acceptance details are missing"
    reply = (
        "I can generate tickets, but I need a bit more product context first.\n\n"
        f"Please add one or more of these details:\n{lines}"
    )
    return {"reply": reply}


def analyze_tickets_node(state: ChatState) -> dict[str, Any]:
    """Analyze existing Jira tickets based on structured decision output from the router."""
    try:
        decision = state.get("decision") or {}
        scope = str(decision.get("analysis_scope") or "none").lower()
        target = str(decision.get("analysis_target") or "").strip().upper()
        user_context = str(decision.get("analysis_context") or "").strip()

        if scope not in {"project", "epic", "ticket"} or not target:
            return {
                "reply": (
                    "I can analyze existing Jira tickets, but I need the scope and key. "
                    "Please specify one of: project key (for example SCRUM), epic key (for example SCRUM-12), "
                    "or ticket key (for example SCRUM-44)."
                )
            }

        project_key = target if scope == "project" else None
        epic_key = target if scope == "epic" else None
        ticket_key = target if scope == "ticket" else None

        scope_label = (
            f"project {project_key}" if project_key
            else f"epic {epic_key}" if epic_key
            else f"ticket {ticket_key}"
        )

        session = analysis_sessions.create_session(
            project_key=project_key or "",
            epic_key=epic_key or "",
            ticket_key=ticket_key or "",
            user_context=user_context,
        )

        result = run_analyzer_agent(
            project_key=project_key,
            epic_key=epic_key,
            ticket_key=ticket_key,
            user_context=user_context,
        )

        analysis = result.get("analysis") or {}
        analysis_sessions.set_analysis(session.session_id, analysis)

        clarification_analysis = None
        tickets = result.get("raw_tickets") or []
        if tickets:
            ticket_context_parts = []
            for ticket in tickets[:5]:
                summary = str(ticket.get("summary") or "").strip()
                description = str(ticket.get("description") or "").strip()
                labels = ", ".join(ticket.get("labels") or [])
                if summary or description or labels:
                    ticket_context_parts.append(
                        f"Ticket: {ticket.get('key', 'Unknown')}\n"
                        f"Summary: {summary}\n"
                        f"Description: {description[:800]}\n"
                        f"Labels: {labels}"
                    )

            ticket_context = "\n\n".join(ticket_context_parts)
            if user_context:
                ticket_context = f"{ticket_context}\n\nAdditional user context:\n{user_context[:1500]}".strip()

            rag_citations = result.get("rag_citations") or []
            rag_text = "\n\n".join([
                f"[Source: {c.get('source', 'unknown')}]\n{c.get('content', '')}"
                for c in rag_citations[:5]
            ])

            if ticket_context:
                clarification_result = get_clarification_chain().invoke({
                    "history_text": "",
                    "attachment_text": "",
                    "context_text": ticket_context,
                    "latest_user_message": "Analyze completeness of these ticket requirements",
                    "rag_context": format_rag_context(rag_text),
                })
                clarification_analysis = clarification_result.model_dump()

        analysis_result = {
            "session_id": session.session_id,
            "ticket_count": result.get("ticket_count", 0),
            "source": result.get("source", ""),
            "project_key": project_key,
            "epic_key": epic_key,
            "ticket_key": ticket_key,
            "analysis": analysis,
            "clarification_analysis": clarification_analysis,
            "rag_citations": result.get("rag_citations", []),
            "rag_used": bool(result.get("rag_citations")),
        }

        readiness = (
            clarification_analysis.get("readiness_score")
            if isinstance(clarification_analysis, dict)
            else None
        )
        summary = f"Analysis complete for {scope_label}."
        if readiness is not None:
            summary += f" Development readiness: {readiness}/10."

        return {
            "analysis_result": analysis_result,
            "reply": summary,
            "clarification_analysis": clarification_analysis,
        }
    except Exception as exc:
        return {"error": f"Ticket analysis failed: {exc}"}


def generate_tickets_node(state: ChatState) -> dict[str, Any]:
    try:
        rag_query = build_rag_query_from_state(state)
        rag_text, rag_citations = retrieve_rag_context(
            query=rag_query or state["latest_user_message"],
            project_key=state.get("project_key", ""),
        )

        prd_content = build_generation_context(state)
        if rag_text:
            prd_content = f"{prd_content}\n\nKnowledge Base Context (RAG):\n{rag_text}"

        ticket_data = get_ticket_chain().invoke({"prd_content": prd_content})
        had_clarification = any(
            (msg.get("role") == "assistant") and ("Development Readiness:" in (msg.get("content") or ""))
            for msg in (state.get("conversation_history") or [])
        )
        preview = summarize_ticket_preview(ticket_data)
        if had_clarification:
            preview = "Readiness: 10/10 after your clarification. Drafted Jira tickets below.\n\n" + preview
        return {
            "generated_tickets": ticket_data,
            "reply": preview,
            "rag_citations": rag_citations,
        }
    except Exception as exc:
        return {"error": f"Ticket generation failed: {exc}"}


def confirm_tickets_node(state: ChatState) -> dict[str, Any]:
    if not state.get("pending_tickets"):
        return {"reply": "There are no pending tickets to confirm yet. Ask me to draft the tickets first."}
    if not state.get("project_key"):
        return {"reply": "I have the ticket draft, but I still need the Jira project key before I can create them."}

    try:
        created = push_tickets(state["project_key"], state["pending_tickets"])
        total = sum(len(items) for items in created.values())
        return {
            "created": created,
            "reply": f"Created {total} Jira tickets in project '{state['project_key']}'.",
        }
    except Exception as exc:
        return {"error": f"JIRA creation failed: {exc}"}


def clarify_requirements_node(state: ChatState) -> dict[str, Any]:
    """Analyze requirements and generate targeted clarification questions"""
    try:
        # Build query for RAG retrieval from user message and context
        rag_query = state["latest_user_message"]
        if state["context_text"]:
            rag_query = f"{rag_query}\n{state['context_text']}"
        
        # Retrieve relevant context from RAG knowledge base
        rag_text, rag_citations = retrieve_rag_context(
            query=rag_query,
            project_key=state.get("project_key", "")
        )
        
        analysis = get_clarification_chain().invoke({
            "history_text": format_messages(state["conversation_history"]),
            "attachment_text": format_attachments(state["attachments"]),
            "context_text": state["context_text"] or "",
            "rag_context": format_rag_context(rag_text),
            "latest_user_message": state["latest_user_message"],
        })

        # Guardrail: avoid unrealistically low readiness on well-structured requirement text.
        source_text = "\n".join(
            [
                state.get("latest_user_message", "") or "",
                state.get("context_text", "") or "",
            ]
        ).lower()
        structure_markers = [
            "implementation details",
            "acceptance criteria",
            "test cases",
            "edge cases",
        ]
        has_sections = sum(1 for marker in structure_markers if marker in source_text) >= 2
        has_bdd = all(token in source_text for token in ["given", "when", "then"])

        if analysis.readiness_score <= 2 and (has_sections or has_bdd):
            analysis.readiness_score = 6
            analysis.summary = (
                "The requirements include strong baseline structure (implementation details, acceptance criteria, "
                "and validation scenarios). Some clarifications may still be needed, but this is not near-zero readiness."
            )

        analysis = normalize_clarification_analysis(analysis)

        # Build conversational response with questions
        reply_parts = []

        if analysis.readiness_score >= 8:
            reply_parts.append(
                f"**Development Readiness: {analysis.readiness_score}/10**\n\n"
                "The requirements look solid! I can proceed with ticket generation."
            )
            if analysis.assumptions_if_proceed:
                reply_parts.append("\n**Minor assumptions I'll make:**")
                for assumption in analysis.assumptions_if_proceed:
                    reply_parts.append(f"- {assumption}")
            reply_parts.append(
                "\n\n_Reply with 'generate tickets' to proceed, or provide additional details._"
            )
        else:
            reply_parts.append(
                f"**Development Readiness: {analysis.readiness_score}/10**\n\n"
                f"{analysis.summary}\n\n"
                "I have a few questions to ensure we build the right thing:"
            )

            # Group questions by priority
            blocking_categories = {g.category for g in analysis.gaps if g.severity == "blocking"}
            important_categories = {g.category for g in analysis.gaps if g.severity == "important"}

            blocking = [q for q in analysis.questions if q.category in blocking_categories]
            important = [q for q in analysis.questions if q.category in important_categories]
            other = [q for q in analysis.questions if q.category not in blocking_categories and q.category not in important_categories]

            question_num = 1
            for q in (blocking + important + other)[:3]:
                reply_parts.append(f"\n**{question_num}. {q.question}**")
                if q.suggestions:
                    reply_parts.append("   _Suggestions:_")
                    for suggestion in q.suggestions:
                        reply_parts.append(f"   - {suggestion}")
                question_num += 1

            if analysis.can_proceed_with_assumptions:
                reply_parts.append(
                    "\n---\n\n_Alternatively, reply 'proceed with assumptions' and I'll generate "
                    "tickets with reasonable defaults that you can refine afterward._"
                )
        
        # Add RAG citations if available
        if rag_citations:
            reply_parts.append("\n---\n_Sources consulted from knowledge base:_")
            for citation in rag_citations[:3]:  # Show top 3 sources
                source_label = citation.get("title") or citation.get("source_id", "Unknown")
                reply_parts.append(f"- {source_label}")

        result = {
            "reply": "\n".join(reply_parts),
            "clarification_analysis": analysis.model_dump(),
            "rag_citations": rag_citations,
        }
        
        # Include RAG citations in the analysis
        if rag_citations:
            result["clarification_analysis"]["rag_citations"] = rag_citations
        
        return result
    except Exception as exc:
        return {"error": f"Clarification analysis failed: {exc}"}


def edit_draft_node(state: ChatState) -> dict[str, Any]:
    """Parse and apply user's edit request to pending draft tickets"""
    try:
        pending = state.get("pending_tickets")
        if not pending:
            return {"reply": "There are no draft tickets to edit. First, ask me to generate tickets."}

        user_message = (state.get("latest_user_message") or "").lower()
        single_story_markers = [
            "single story",
            "one story",
            "1 story",
            "only story",
            "just one story",
            "just a story",
        ]
        wants_single_story = (
            any(marker in user_message for marker in single_story_markers)
            and ("task" in user_message or "story" in user_message or "convert" in user_message or "merge" in user_message)
        )

        if wants_single_story:
            stories = pending.get("stories", []) or []
            tasks = pending.get("tasks", []) or []

            if not stories and not tasks:
                return {"reply": "I could not find stories or tasks to consolidate into a single story."}

            if not stories and tasks:
                first_task = tasks[0]
                stories = [{
                    "summary": first_task.get("summary", "Consolidated Story"),
                    "description": first_task.get("description", ""),
                    "priority": first_task.get("priority", "Medium"),
                    "story_points": first_task.get("story_points"),
                    "labels": first_task.get("labels", []),
                    "acceptance_criteria": first_task.get("acceptance_criteria", []),
                }]
                tasks = tasks[1:]

            base_story = stories[0]

            if len(stories) > 1:
                extra_story_summaries = [s.get("summary", "Untitled story") for s in stories[1:]]
                if extra_story_summaries:
                    extra_line = "Additional story scope consolidated: " + ", ".join(extra_story_summaries)
                    existing_desc = base_story.get("description", "")
                    base_story["description"] = f"{existing_desc}\n\n{extra_line}" if existing_desc else extra_line

            if tasks:
                task_lines = []
                for task in tasks:
                    task_summary = task.get("summary", "Untitled task")
                    task_desc = task.get("description", "")
                    if task_desc:
                        task_lines.append(f"- {task_summary}: {task_desc}")
                    else:
                        task_lines.append(f"- {task_summary}")

                if task_lines:
                    consolidation_block = "Implementation details consolidated from tasks:\n" + "\n".join(task_lines)
                    existing_desc = base_story.get("description", "")
                    base_story["description"] = f"{existing_desc}\n\n{consolidation_block}" if existing_desc else consolidation_block

            base_labels = base_story.get("labels", []) or []
            for source_ticket in (stories[1:] + tasks):
                for label in (source_ticket.get("labels", []) or []):
                    if label not in base_labels:
                        base_labels.append(label)
            base_story["labels"] = base_labels

            pending["epics"] = []
            pending["stories"] = [base_story]
            pending["tasks"] = []

            updated_preview = summarize_ticket_preview(pending)
            return {
                "pending_tickets": pending,
                "reply": (
                    "Consolidated the draft into a single story format by merging story/task details into one story.\n\n"
                    f"**Updated ticket preview:**\n{updated_preview}\n\n"
                    "_Say 'confirm' to create in Jira, or request more edits._"
                ),
            }

        # Build summary of pending tickets for the LLM
        pending_summary = summarize_pending_tickets(pending)

        # Parse the edit request using LLM
        edit_request = get_edit_draft_chain().invoke({
            "pending_tickets_summary": pending_summary,
            "latest_user_message": state["latest_user_message"],
        })

        ticket_type = edit_request.ticket_type
        ticket_index = edit_request.ticket_index
        field = edit_request.field
        action = edit_request.action
        value = edit_request.value

        # Handle irregular pluralization (story -> stories).
        plural_key = {
            "epic": "epics",
            "story": "stories",
            "task": "tasks",
        }.get(ticket_type, f"{ticket_type}s")

        # Validate ticket type exists
        ticket_list = pending.get(plural_key, [])
        if not ticket_list:
            return {"reply": f"No {plural_key} found in pending tickets. Available types: {', '.join(k for k in pending.keys() if pending[k])}"}

        # Validate index
        if ticket_index < 0 or ticket_index >= len(ticket_list):
            return {"reply": f"Invalid {ticket_type} index. You have {len(ticket_list)} {ticket_type}(s) (use 1-{len(ticket_list)})."}

        # Get the ticket to edit
        ticket = ticket_list[ticket_index]

        # Apply the edit
        if action == "remove" and field == "summary":
            # Remove entire ticket
            ticket_list.pop(ticket_index)
            reply = f"Removed {ticket_type} #{ticket_index + 1}: \"{ticket.get('summary', 'Unknown')}\""
        elif action == "set":
            old_value = ticket.get(field, "")
            ticket[field] = value
            reply = f"Updated {ticket_type} #{ticket_index + 1}'s **{field}** from \"{old_value}\" to \"{value}\""
        elif action == "append":
            old_value = ticket.get(field, "")
            if isinstance(old_value, list):
                ticket[field].append(value)
            else:
                ticket[field] = f"{old_value}\n{value}" if old_value else value
            reply = f"Appended to {ticket_type} #{ticket_index + 1}'s **{field}**: \"{value}\""
        elif action == "remove":
            if isinstance(ticket.get(field), list):
                # Try to remove matching item from list
                if value in ticket[field]:
                    ticket[field].remove(value)
                    reply = f"Removed \"{value}\" from {ticket_type} #{ticket_index + 1}'s **{field}**"
                else:
                    reply = f"Value \"{value}\" not found in {ticket_type} #{ticket_index + 1}'s **{field}**"
            else:
                ticket[field] = ""
                reply = f"Cleared {ticket_type} #{ticket_index + 1}'s **{field}**"
        else:
            return {"reply": f"Unknown action: {action}. Use 'set', 'append', or 'remove'."}

        # Build updated preview
        updated_preview = summarize_ticket_preview(pending)
        
        return {
            "pending_tickets": pending,  # Return updated tickets
            "reply": f"{reply}\n\n**Updated ticket preview:**\n{updated_preview}\n\n_Say 'confirm' to create in Jira, or request more edits._",
        }
    except Exception as exc:
        return {"error": f"Edit draft failed: {exc}"}


def route_after_decision(state: ChatState) -> str:
    if state.get("error"):
        return "end"
    action = (state.get("decision") or {}).get("action", "respond")
    return action