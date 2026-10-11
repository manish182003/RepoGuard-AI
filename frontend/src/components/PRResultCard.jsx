import React from 'react';
import { GitPullRequest, ExternalLink, CheckCircle, AlertCircle } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const PRResultCard = () => {
  const { prResult } = useInvestigation();

  if (!prResult) return null;

  if (prResult.success) {
    return (
      <div className="pr-success-card">
        <div className="pr-success-left">
          <div className="pr-icon-badge">
            <CheckCircle size={26} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc', marginBottom: 4 }}>
              GitHub Pull Request Created Successfully!
            </h3>
            <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
              {prResult.pr_number
                ? `PR #${prResult.pr_number} is open and ready for maintainer review.`
                : 'Pull Request has been published.'}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          {prResult.html_url && (
            <a
              href={prResult.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="pr-link-btn"
            >
              <GitPullRequest size={16} />
              View Pull Request
              <ExternalLink size={14} />
            </a>
          )}

          {prResult.upstream_compare_url && (
            <a
              href={prResult.upstream_compare_url}
              target="_blank"
              rel="noopener noreferrer"
              className="pr-link-btn"
              style={{ background: '#0284c7' }}
            >
              <GitPullRequest size={16} />
              Open Upstream PR
              <ExternalLink size={14} />
            </a>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'rgba(244, 63, 94, 0.1)',
        border: '1px solid #f43f5e',
        borderRadius: '12px',
        padding: '18px 24px',
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
        marginTop: '10px',
      }}
    >
      <AlertCircle size={28} color="#f43f5e" />
      <div>
        <h4 style={{ color: '#fda4af', fontSize: '0.95rem', fontWeight: 600 }}>Pull Request Blocked</h4>
        <p style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>{prResult.error || 'Failed to create pull request.'}</p>
      </div>
    </div>
  );
};

export default PRResultCard;
