import React, { createContext, useContext, useState, useRef } from 'react';

const InvestigationContext = createContext(null);

export const InvestigationProvider = ({ children }) => {
  const [repositoryUrl, setRepositoryUrl] = useState('https://github.com/bottlepy/bottle');
  const [targetIssueNumber, setTargetIssueNumber] = useState('1470');
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [activeStep, setActiveStep] = useState(0); // 0: Idle, 1: Context, 2: AST, 3: Targeted, 4: Loop, 5: Sandbox, 6: Approval, 7: PR
  
  const [targetedIssue, setTargetedIssue] = useState(null);
  const [events, setEvents] = useState([]);
  const [findings, setFindings] = useState([]);
  const [patches, setPatches] = useState([]);
  const [pendingApproval, setPendingApproval] = useState(null);
  const [prResult, setPrResult] = useState(null);
  const [stats, setStats] = useState({
    totalFiles: 0,
    analyzedCount: 0,
    iterationsUsed: 0,
    sandboxPassed: null,
  });

  const abortControllerRef = useRef(null);

  const addEvent = (type, data) => {
    const time = new Date().toLocaleTimeString();
    setEvents((prev) => [...prev, { id: `${Date.now()}-${Math.random()}`, time, type, data }]);
  };

  const startInvestigation = async (customUrl, customIssue) => {
    const url = customUrl !== undefined ? customUrl : repositoryUrl;
    const issue = customIssue !== undefined ? customIssue : targetIssueNumber;

    if (!url.trim()) return;

    setIsInvestigating(true);
    setActiveStep(1);
    setEvents([]);
    setFindings([]);
    setPatches([]);
    setPendingApproval(null);
    setPrResult(null);
    setTargetedIssue(null);
    setStats({ totalFiles: 0, analyzedCount: 0, iterationsUsed: 0, sandboxPassed: null });

    addEvent('system', { message: `Connecting to /investigation/stream for ${url}${issue ? ` (Targeting Issue #${issue})` : ''}...` });

    abortControllerRef.current = new AbortController();

    const payload = {
      repository_url: url,
      auto_generate_patch: true,
      human_approved_for_pr: false,
    };
    if (issue && !isNaN(parseInt(issue, 10))) {
      payload.target_issue_number = parseInt(issue, 10);
    }

    try {
      const response = await fetch('/investigation/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
          if (part.startsWith('data: ')) {
            const jsonStr = part.replace('data: ', '').trim();
            if (jsonStr) {
              try {
                const parsed = JSON.parse(jsonStr);
                handleStreamEvent(parsed.event, parsed.data);
              } catch (e) {
                console.error('Error parsing SSE event:', e);
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        addEvent('error', { message: err.message || 'Stream connection failed' });
      }
    } finally {
      setIsInvestigating(false);
    }
  };

  const handleStreamEvent = (eventType, data) => {
    addEvent(eventType, data);

    switch (eventType) {
      case 'pipeline_started':
      case 'context_fetching':
      case 'metadata_fetched':
      case 'tree_fetched':
      case 'files_selected':
      case 'files_fetching_progress':
      case 'issues_fetched':
        setActiveStep(1);
        if (data.total_files) {
          setStats((prev) => ({ ...prev, totalFiles: data.total_files }));
        }
        break;
      case 'files_filtered':
      case 'ast_scan_started':
      case 'ast_scan_progress':
      case 'ast_rule_finding':
        setActiveStep(2);
        setStats((prev) => ({
          ...prev,
          totalFiles: data.total_files || prev.totalFiles,
          analyzedCount: data.analyzable_count || data.scanned || prev.analyzedCount,
        }));
        break;
      case 'issue_fetching_direct':
      case 'jev_triaging_issue':
      case 'jev_triage_result':
      case 'issue_targeted':
        setActiveStep(3);
        if (eventType === 'issue_targeted') {
          setTargetedIssue(data);
        }
        break;
      case 'agent_investigation_started':
      case 'agent_iteration_started':
      case 'agent_tool_calling':
      case 'agent_tool_result':
        setActiveStep(4);
        break;
      case 'hypothesis_validated':
        setFindings((prev) => {
          if (prev.some((f) => f.id === data.id)) return prev;
          return [...prev, data];
        });
        break;
      case 'patch_generating':
      case 'patch_verifying_ast':
        setActiveStep(5);
        break;
      case 'sandbox_executing_pytest':
        setActiveStep(5);
        break;
      case 'sandbox_pytest_completed':
        setStats((prev) => ({ ...prev, sandboxPassed: data.success }));
        break;
      case 'human_approval_required':
        setActiveStep(6);
        setPendingApproval(data);
        break;
      case 'pipeline_completed':
        if (data.findings) setFindings(data.findings);
        if (data.patches) setPatches(data.patches);
        if (data.iterations_used) {
          setStats((prev) => ({ ...prev, iterationsUsed: data.iterations_used }));
        }
        if (!pendingApproval) {
          setActiveStep(7);
        }
        break;
      case 'pipeline_failed':
        addEvent('error', { message: data.error });
        break;
      default:
        break;
    }
  };

  const approvePR = async (approved) => {
    if (!pendingApproval || !pendingApproval.job_id) return;

    addEvent('system', { message: `Submitting human approval (approved=${approved}) for ${pendingApproval.job_id}...` });

    try {
      const res = await fetch('/investigation/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: pendingApproval.job_id,
          human_approved_for_pr: approved,
        }),
      });

      const result = await res.json();
      addEvent('approval_result', result);

      if (approved && result.pr_result) {
        setPrResult(result.pr_result);
        setActiveStep(7);
      }
      setPendingApproval(null);
    } catch (err) {
      addEvent('error', { message: `Approval submission failed: ${err.message}` });
    }
  };

  const stopInvestigation = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsInvestigating(false);
      addEvent('system', { message: 'Investigation stopped by user.' });
    }
  };

  return (
    <InvestigationContext.Provider
      value={{
        repositoryUrl,
        setRepositoryUrl,
        targetIssueNumber,
        setTargetIssueNumber,
        isInvestigating,
        activeStep,
        targetedIssue,
        events,
        findings,
        patches,
        pendingApproval,
        prResult,
        stats,
        startInvestigation,
        stopInvestigation,
        approvePR,
      }}
    >
      {children}
    </InvestigationContext.Provider>
  );
};

export const useInvestigation = () => {
  const context = useContext(InvestigationContext);
  if (!context) {
    throw new Error('useInvestigation must be used within an InvestigationProvider');
  }
  return context;
};
