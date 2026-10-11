import React from 'react';
import { Play, Square, Sparkles, FolderGit2, Hash } from 'lucide-react';
import { useInvestigation } from '../context/InvestigationContext';

const PRESETS = [
  {
    name: 'Bottle #1470',
    desc: 'MultipartParser memory limit',
    url: 'https://github.com/bottlepy/bottle',
    issue: '1470',
  },
  {
    name: 'Marshmallow #3019',
    desc: 'Negative POSIX timestamp deserialization',
    url: 'https://github.com/marshmallow-code/marshmallow',
    issue: '3019',
  },
  {
    name: 'SQLite-Utils #892',
    desc: 'rows_from_file format kwargs',
    url: 'https://github.com/simonw/sqlite-utils',
    issue: '892',
  },
];

const ControlBar = () => {
  const {
    repositoryUrl,
    setRepositoryUrl,
    targetIssueNumber,
    setTargetIssueNumber,
    isInvestigating,
    startInvestigation,
    stopInvestigation,
  } = useInvestigation();

  const handlePreset = (preset) => {
    setRepositoryUrl(preset.url);
    setTargetIssueNumber(preset.issue);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isInvestigating) {
      stopInvestigation();
    } else {
      startInvestigation();
    }
  };

  return (
    <div className="control-card">
      <div className="control-header">
        <h2>
          <Sparkles size={18} color="#38bdf8" />
          Autonomous Target Configuration
        </h2>
        <div className="preset-picker">
          <span>Quick Presets:</span>
          {PRESETS.map((p) => (
            <button
              key={p.name}
              type="button"
              className="preset-btn"
              onClick={() => handlePreset(p)}
              disabled={isInvestigating}
              title={p.desc}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="input-row">
          <div className="input-field repo">
            <label htmlFor="repo-input">
              <FolderGit2 size={12} style={{ display: 'inline', marginRight: 4 }} />
              GitHub Repository URL
            </label>
            <input
              id="repo-input"
              type="url"
              value={repositoryUrl}
              onChange={(e) => setRepositoryUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              disabled={isInvestigating}
              required
            />
          </div>

          <div className="input-field issue">
            <label htmlFor="issue-input">
              <Hash size={12} style={{ display: 'inline', marginRight: 4 }} />
              Target Issue # (Optional)
            </label>
            <input
              id="issue-input"
              type="number"
              value={targetIssueNumber}
              onChange={(e) => setTargetIssueNumber(e.target.value)}
              placeholder="e.g. 1470"
              disabled={isInvestigating}
            />
          </div>

          <button
            type="submit"
            className="action-btn"
            style={{
              background: isInvestigating
                ? 'linear-gradient(135deg, #f43f5e, #be123c)'
                : undefined,
            }}
          >
            {isInvestigating ? (
              <>
                <Square size={16} fill="white" />
                Stop Agent
              </>
            ) : (
              <>
                <Play size={16} fill="white" />
                Start Investigation
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ControlBar;
