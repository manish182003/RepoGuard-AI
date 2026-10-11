import React from 'react';
import { InvestigationProvider } from './context/InvestigationContext';
import Header from './components/Header';
import ControlBar from './components/ControlBar';
import PipelineStepper from './components/PipelineStepper';
import ApprovalBanner from './components/ApprovalBanner';
import PRResultCard from './components/PRResultCard';
import LiveTerminal from './components/LiveTerminal';
import FindingsList from './components/FindingsList';
import './index.css';

function Dashboard() {
  return (
    <div className="app-container">
      <Header />
      <main className="main-dashboard">
        <ControlBar />
        <PipelineStepper />
        <ApprovalBanner />
        <PRResultCard />

        <div className="dashboard-grid">
          <LiveTerminal />
          <FindingsList />
        </div>
      </main>
    </div>
  );
}

function App() {
  return (
    <InvestigationProvider>
      <Dashboard />
    </InvestigationProvider>
  );
}

export default App;