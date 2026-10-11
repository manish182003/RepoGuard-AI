import React, { useEffect, useRef } from 'react';
import { Terminal, Radio, PauseCircle } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const LiveTerminal = () => {
  const { events, isInvestigating } = useInvestigation();
  const terminalEndRef = useRef(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="panel-card">
      <div className="panel-header">
        <div className="panel-title">
          <Terminal size={18} color="#38bdf8" />
          Live Event Stream (SSE)
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {isInvestigating ? (
            <span className="panel-badge" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Radio size={12} className="pulse" />
              Streaming Active
            </span>
          ) : (
            <span className="panel-badge" style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}>
              <PauseCircle size={12} />
              Idle
            </span>
          )}
          <span className="panel-badge">{events.length} events</span>
        </div>
      </div>

      <div className="panel-body" style={{ padding: '12px' }}>
        <div className="terminal-window">
          {events.length === 0 ? (
            <div style={{ color: '#475569', textAlign: 'center', margin: 'auto' }}>
              No active session. Select a target repository and click <strong>Start Investigation</strong>.
            </div>
          ) : (
            events.map((evt) => {
              const eventClass = `terminal-event event-${evt.type}`;
              const dataSnippet = formatEventData(evt.type, evt.data);

              return (
                <div key={evt.id} className="terminal-line">
                  <span className="terminal-time">[{evt.time}]</span>
                  <span className={eventClass}>{evt.type}</span>
                  <span className="terminal-text">{dataSnippet}</span>
                </div>
              );
            })
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
};

function formatEventData(type, data) {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (data.message) return data.message;
  if (data.error) return `Error: ${data.error}`;

  switch (type) {
    case 'pipeline_started':
      return `Target: ${data.repository_url}`;
    case 'metadata_fetched':
      return `Metadata retrieved: ${data.full_name || `${data.owner}/${data.name}`} (${data.stars}★ | branch: ${data.default_branch})`;
    case 'tree_fetched':
      return `Git tree parsed: ${data.total_files} total files discovered in branch '${data.default_branch}'`;
    case 'files_selected':
      return `Selected ${data.count} code files for analysis (${data.total_tree} total in tree)`;
    case 'files_fetching_progress':
      return `[Fetch] ${data.completed}/${data.total} files (${data.percent}%) ➔ ${data.current_file}`;
    case 'issues_fetched':
      return `Retrieved ${data.count} issues from GitHub API (${data.state})`;
    case 'files_filtered':
      return `Filtered ${data.analyzable_count} analyzable files out of ${data.total_files} total`;
    case 'ast_scan_started':
      return data.message || `Analyzing ${data.total_files} files with AST static rules...`;
    case 'ast_scan_progress':
      return `[AST Scan] ${data.scanned}/${data.total} files (${data.percent}%) | Findings: ${data.findings_count} ➔ ${data.current_file}`;
    case 'ast_rule_finding':
      return `[AST Rule Detected] ${data.rule} at ${data.path}:${data.line} ("${data.title}")`;
    case 'issue_fetching_direct':
      return data.message || `Fetching targeted Issue #${data.issue_number} from GitHub API...`;
    case 'jev_triaging_issue':
      return `[TypeSafe Jev] Triaging Issue #${data.issue_number}: "${data.title}"...`;
    case 'jev_triage_result':
      return `[TypeSafe Jev] Issue #${data.issue_number}: P(bug)=${Math.round((data.bug_probability || 0) * 100)}% | Category=${data.category}`;
    case 'issue_targeted':
      return `Issue #${data.number}: "${data.title}" by @${data.author || 'user'}`;
    case 'duplicate_pr_detected':
      return `⚠️ DUPLICATE PR WARNING: An open PR already exists for Issue #${data.issue_number}: PR #${data.existing_pr?.pr_number} ("${data.existing_pr?.title}") by @${data.existing_pr?.author || 'contributor'}`;
    case 'agent_iteration_started':
      return `Turn ${data.iteration}/${data.max_iterations} reasoning & tool planning`;
    case 'agent_tool_calling':
      return `Calling ${data.tool_name}(${JSON.stringify(data.arguments || {})})`;
    case 'agent_tool_result':
      return `Tool ${data.tool_name} returned: ${JSON.stringify(data.output_snippet || data.success)}`;
    case 'agent_finalized':
      return `Investigation finalized: ${data.summary?.slice(0, 140)}...`;
    case 'hypothesis_validated':
      return `Finding validated: ${data.title} at ${data.path}:${data.line} (Confidence: ${Math.round((data.confidence || 0) * 100)}%)`;
    case 'patch_generating':
      return `Synthesizing minimal fix for ${data.path}`;
    case 'patch_verifying_ast':
      return `Validating Python AST grammar for ${data.path}`;
    case 'sandbox_executing_pytest':
      return `Executing isolated pytest subprocess sandbox for ${data.path}`;
    case 'sandbox_pytest_completed':
      return `Sandbox completed with exit code ${data.exit_code} (Success: ${data.success})`;
    case 'human_approval_required':
      return `Approval needed for ${data.target_repository} (${data.patch_path}) [Job ID: ${data.job_id}]`;
    case 'approval_result':
      return `Decision: ${data.status} | Result: ${JSON.stringify(data.pr_result || {})}`;
    default:
      return JSON.stringify(data);
  }
}

export default LiveTerminal;
