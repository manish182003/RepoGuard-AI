import React from 'react';
import { Bug, Target, FileText, CheckCircle2, ShieldCheck, ExternalLink } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const FindingsList = () => {
  const { findings, targetedIssue, stats } = useInvestigation();

  return (
    <div className="panel-card">
      <div className="panel-header">
        <div className="panel-title">
          <Bug size={18} color="#f59e0b" />
          Validated Findings & Hypotheses
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <span className="panel-badge">{findings.length} findings</span>
          {stats.totalFiles > 0 && (
            <span className="panel-badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: '#818cf8' }}>
              {stats.analyzedCount} / {stats.totalFiles} files
            </span>
          )}
        </div>
      </div>

      <div className="panel-body">
        {targetedIssue && (
          <div
            style={{
              background: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              borderRadius: '8px',
              padding: '14px',
              marginBottom: '16px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#38bdf8', fontWeight: 600, fontSize: '0.85rem' }}>
                <Target size={16} />
                Targeted Issue #{targetedIssue.number}
              </div>
              {targetedIssue.url && (
                <a
                  href={targetedIssue.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#94a3b8', fontSize: '0.75rem', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}
                >
                  GitHub <ExternalLink size={12} />
                </a>
              )}
            </div>
            <h4 style={{ color: '#f1f5f9', fontSize: '0.95rem', fontWeight: 600 }}>{targetedIssue.title}</h4>
            {targetedIssue.author && (
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Reported by @{targetedIssue.author}</span>
            )}
          </div>
        )}

        {findings.length === 0 ? (
          <div style={{ color: '#475569', textAlign: 'center', padding: '40px 0' }}>
            <ShieldCheck size={36} color="#334155" style={{ margin: '0 auto 12px', display: 'block' }} />
            No confirmed defects yet. Agent will gather evidence using AST & code grep tools.
          </div>
        ) : (
          findings.map((f, idx) => {
            const sevClass = `severity-pill sev-${f.severity || 'medium'}`;
            const confPercent = Math.round((f.confidence || 0) * 100);

            return (
              <div key={f.id || idx} className="finding-item">
                <div className="finding-header">
                  <h4 className="finding-title">{f.title || f.rule}</h4>
                  <span className={sevClass}>{f.severity || 'medium'}</span>
                </div>

                <div className="finding-location">
                  <FileText size={12} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                  {f.path}:{f.line}
                  <span style={{ marginLeft: 12, color: '#94a3b8' }}>
                    Confidence: <strong>{confPercent}%</strong>
                  </span>
                </div>

                <p className="finding-desc">{f.description}</p>

                {f.evidence && f.evidence.length > 0 && (
                  <div className="code-snippet">
                    {f.evidence.map((line, lIdx) => (
                      <div key={lIdx} style={{ whiteSpace: 'pre' }}>
                        {line}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default FindingsList;
