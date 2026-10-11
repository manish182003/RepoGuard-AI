import React from 'react';
import { AlertTriangle, CheckCircle2, XCircle, GitPullRequest, FileCode } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const ApprovalBanner = () => {
  const { pendingApproval, approvePR } = useInvestigation();

  if (!pendingApproval) return null;

  const targetRepo = pendingApproval.target_repository || 'repository';
  const patchPath = pendingApproval.patch_path || 'source.py';
  const summary = pendingApproval.patch_summary || 'Verified code repair.';
  const modifiedContent = pendingApproval.modified_content;

  return (
    <div className="approval-banner">
      <div className="approval-header">
        <div className="approval-title">
          <AlertTriangle size={24} color="#f59e0b" />
          <span>Security Safeguard: Human Approval Required</span>
        </div>

        <div className="approval-actions">
          <button
            type="button"
            className="btn-approve"
            onClick={() => approvePR(true)}
          >
            <CheckCircle2 size={16} />
            Approve & Open PR
          </button>
          <button
            type="button"
            className="btn-reject"
            onClick={() => approvePR(false)}
          >
            <XCircle size={16} />
            Reject
          </button>
        </div>
      </div>

      <p style={{ color: '#cbd5e1', fontSize: '0.9rem', lineHeight: '1.5' }}>
        The autonomous agent verified this defect patch using AST grammar analysis and subprocess sandbox execution. 
        Before forking <strong>{targetRepo}</strong> and opening a GitHub Pull Request, human confirmation is required.
      </p>

      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', fontSize: '0.82rem', color: '#94a3b8' }}>
        <div>
          <FileCode size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          Target: <strong style={{ color: '#38bdf8' }}>{patchPath}</strong>
        </div>
        <div>
          <GitPullRequest size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          Target Repository: <strong style={{ color: '#f1f5f9' }}>{targetRepo}</strong>
        </div>
        {pendingApproval.jev_risk_tier && (
          <div style={{ background: 'rgba(192, 132, 252, 0.12)', padding: '2px 10px', borderRadius: '4px', border: '1px solid rgba(192, 132, 252, 0.3)', color: '#d8b4fe' }}>
            <span>⚡ Jev Decision: <strong>{pendingApproval.jev_risk_tier.toUpperCase()} RISK</strong></span>
            {pendingApproval.jev_safety_score !== undefined && (
              <span style={{ marginLeft: 6 }}>
                (Safety: {Math.round(pendingApproval.jev_safety_score * 100)}%)
              </span>
            )}
          </div>
        )}
      </div>

      {pendingApproval.existing_pr && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          borderRadius: '8px',
          padding: '12px 16px',
          marginTop: '12px',
          marginBottom: '12px',
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-start'
        }}>
          <AlertTriangle size={20} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div style={{ fontSize: '0.85rem', color: '#fca5a5' }}>
            <strong style={{ color: '#f87171' }}>⚠️ Potential Duplicate PR Detected:</strong>
            <div style={{ marginTop: '4px', color: '#e2e8f0' }}>
              An open Pull Request already addresses this issue:{' '}
              <a
                href={pendingApproval.existing_pr.html_url}
                target="_blank"
                rel="noreferrer"
                style={{ color: '#38bdf8', textDecoration: 'underline', fontWeight: 600 }}
              >
                PR #{pendingApproval.existing_pr.pr_number} (&quot;{pendingApproval.existing_pr.title}&quot;)
              </a>
              {pendingApproval.existing_pr.author && ` by @${pendingApproval.existing_pr.author}`}.
            </div>
            <div style={{ marginTop: '4px', fontSize: '0.78rem', color: '#94a3b8' }}>
              Submitting another PR may create a duplicate on the open source repository. Please review the existing PR before approving.
            </div>
          </div>
        </div>
      )}

      <div className="diff-card">
        <div className="diff-header">
          <span>Proposed Solution Rationale</span>
          <span>Job ID: {pendingApproval.job_id}</span>
        </div>
        <div className="diff-body" style={{ color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
          {summary}
        </div>
      </div>
    </div>
  );
};

export default ApprovalBanner;
