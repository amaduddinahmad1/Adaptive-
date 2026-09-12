import React from 'react';
import Timer from '../common/Timer';
import { INTERVIEW_STATUS } from '../../types/interview';

const InterviewHeader = ({ candidateName, role, status, elapsedTime }) => {
  return (
    <header className="flex shrink-0 items-center justify-between px-8 py-5 sm:px-12 lg:px-16 xl:px-24">
      <div className="flex min-w-0 items-baseline gap-3">
        <p className="truncate font-sans text-sm font-medium text-text">
          {candidateName || 'Candidate'}
        </p>
        <p className="truncate font-sans text-sm text-text-muted">
          {role || 'Role'}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-5">
        {status === INTERVIEW_STATUS.IN_PROGRESS && (
          <span className="inline-flex items-center gap-2 font-sans text-xs text-text-muted">
            <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
            Live
          </span>
        )}
        <Timer seconds={elapsedTime} />
      </div>
    </header>
  );
};

export default InterviewHeader;
