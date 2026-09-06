import React from 'react';
import Badge from '../common/Badge';
import Timer from '../common/Timer';
import { INTERVIEW_STATUS } from '../../types/interview';
import './InterviewHeader.css';

const InterviewHeader = ({ candidateName, role, status, elapsedTime }) => {
  return (
    <header className="interview-header">
      <div className="header-left">
        <h2 className="candidate-name">{candidateName || 'Candidate'}</h2>
        <Badge variant="info">{role || 'Role'}</Badge>
      </div>
      
      <div className="header-right">
        {status === INTERVIEW_STATUS.IN_PROGRESS && (
          <Badge variant="success" dot={true}>Live</Badge>
        )}
        <Timer seconds={elapsedTime} />
      </div>
    </header>
  );
};

export default InterviewHeader;
