import React from 'react';
import { useInvestigation } from '../context/InvestigationContext';
import { Check, CircleDot } from 'lucide-react';

const STEPS = [
  { id: 1, label: 'Context Retrieval' },
  { id: 2, label: 'Static AST Filter' },
  { id: 3, label: 'Issue Objective' },
  { id: 4, label: 'ReAct Agent Loop' },
  { id: 5, label: 'Patch AST Check' },
  { id: 6, label: 'Pytest Sandbox' },
  { id: 7, label: 'Human Checkpoint' },
  { id: 8, label: 'Pull Request' },
];

const PipelineStepper = () => {
  const { activeStep } = useInvestigation();

  return (
    <div className="stepper-card">
      <div className="steps-list">
        {STEPS.map((step) => {
          const isCompleted = activeStep > step.id;
          const isActive = activeStep === step.id;

          let itemClass = 'step-item';
          if (isCompleted) itemClass += ' completed';
          if (isActive) itemClass += ' active';

          return (
            <div key={step.id} className={itemClass}>
              <div className="step-circle">
                {isCompleted ? (
                  <Check size={16} color="#ffffff" />
                ) : isActive ? (
                  <CircleDot size={16} color="#07090e" />
                ) : (
                  step.id
                )}
              </div>
              <span className="step-label">{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PipelineStepper;
