import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import DraftTicketCard from "./DraftTicketCard";
import API_BASE_URL from "../config";

function DraftPanel({ tickets, onUpdate, onDelete, onCreate, isCreating, canCreate, projectKey, onProjectKeyChange }) {
  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [projectsError, setProjectsError] = useState("");

  useEffect(() => {
    async function fetchProjects() {
      setLoadingProjects(true);
      setProjectsError("");
      try {
        const response = await fetch(`${API_BASE_URL}/projects`);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Failed to fetch projects");
        }
        setProjects(data.projects || []);
      } catch (error) {
        console.error("Failed to fetch JIRA projects:", error);
        setProjectsError(error.message);
      } finally {
        setLoadingProjects(false);
      }
    }
    fetchProjects();
  }, []);
  const handleUpdate = (index, type, updatedTicket) => {
    const normalizedType = type === 'Bug' ? 'Task' : type;
    const key = normalizedType.toLowerCase() + 's';
    const list = [...(tickets[key] || [])];
    list[index] = updatedTicket;
    onUpdate({ ...tickets, [key]: list });
  };

  const handleDelete = (index, type) => {
    const normalizedType = type === 'Bug' ? 'Task' : type;
    const key = normalizedType.toLowerCase() + 's';
    const list = (tickets[key] || []).filter((_, i) => i !== index);
    onUpdate({ ...tickets, [key]: list });
  };

  const epicCount = (tickets.epics || []).length;
  const storyCount = (tickets.stories || []).length;
  const taskCount = (tickets.tasks || []).length;
  const bugCount = (tickets.tasks || []).filter(
    (ticket) => String(ticket?.issue_type || '').toLowerCase() === 'bug' || (ticket?.labels || []).includes('bug')
  ).length;
  const totalCount = epicCount + storyCount + taskCount;

  return (
    <div className="draft-panel">
      <div className="draft-panel-header">
        <div>
          <p className="panel-kicker">Draft</p>
          <h3>Pending ticket overview</h3>
        </div>
        <div className="draft-stats">
          <span className="stat-pill epic">{epicCount} Epics</span>
          <span className="stat-pill story">{storyCount} Stories</span>
          <span className="stat-pill task">{taskCount} Tasks{bugCount ? ` (${bugCount} Bug${bugCount === 1 ? '' : 's'})` : ''}</span>
        </div>
      </div>

      <div className="project-key-row">
        <label>JIRA Project</label>
        <div className="project-key-input-group">
          {loadingProjects ? (
            <div className="project-key-input loading">Loading projects...</div>
          ) : projectsError ? (
            <input
              type="text"
              value={projectKey || ''}
              onChange={(e) => onProjectKeyChange(e.target.value.toUpperCase())}
              placeholder="e.g., KAN"
              className="project-key-input"
              title={`Failed to load projects: ${projectsError}`}
            />
          ) : (
            <div className="project-select-wrapper">
              <select
                value={projectKey || ''}
                onChange={(e) => onProjectKeyChange(e.target.value)}
                className="project-key-select"
              >
                <option value="">Select a project...</option>
                {projects.map((project) => (
                  <option key={project.key} value={project.key}>
                    {project.key} - {project.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="select-icon" />
            </div>
          )}
          {!projectKey && <span className="project-key-hint">Required to create tickets</span>}
        </div>
      </div>

      {totalCount === 0 ? (
        <p className="muted-copy">No tickets drafted yet. Start a conversation to create tickets.</p>
      ) : (
        <div className="draft-ticket-list">
          {(tickets.epics || []).map((ticket, i) => (
            <DraftTicketCard
              key={`epic-${i}`}
              ticket={ticket}
              type="Epic"
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          {(tickets.stories || []).map((ticket, i) => (
            <DraftTicketCard
              key={`story-${i}`}
              ticket={ticket}
              type="Story"
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          {(tickets.tasks || []).map((ticket, i) => (
            <DraftTicketCard
              key={`task-${i}`}
              ticket={ticket}
              type={String(ticket?.issue_type || '').toLowerCase() === 'bug' || (ticket?.labels || []).includes('bug') ? 'Bug' : 'Task'}
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <div className="draft-panel-footer">
        <button
          className="create-tickets-btn"
          onClick={onCreate}
          disabled={!canCreate || isCreating || totalCount === 0}
        >
          {isCreating ? "Creating in JIRA..." : `Create ${totalCount} ticket(s) in JIRA`}
        </button>
        {!canCreate && totalCount > 0 && (
          <p className="draft-hint">Specify a project key (e.g., "in project KAN") to enable creation</p>
        )}
      </div>
    </div>
  );
}

export default DraftPanel;
