import React from 'react';
import { Shield, Cpu, Activity } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const Header = () => {
  const { isInvestigating } = useInvestigation();

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-icon">
          <Shield size={22} color="#ffffff" />
        </div>
        <div className="brand-text">
          <h1>RepoGuard AI</h1>
          <span>Autonomous Code Repair & Remediation</span>
        </div>
      </div>

      <div className="header-badges">
        <div className="cascade-badge" title="TypeSafe Jev System One Decision Model for Issue Triage & Risk Guardrails">
          <Activity size={14} color="#c084fc" />
          <span>TypeSafe Jev: Active</span>
        </div>

        <div className="cascade-badge" title="3-Tier Resilient Fallback Cascade configured">
          <Cpu size={14} color="#38bdf8" />
          <span>LLM: Groq ➔ Cloudflare Workers AI ➔ Secondary</span>
        </div>

        <div className="cascade-badge">
          <span className={`pulse ${isInvestigating ? 'investigating' : ''}`} />
          <span>{isInvestigating ? 'Agent Active' : 'System Ready'}</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
