import React from 'react';
import Button from '../common/Button';
import './InterviewControls.css';

const InterviewControls = ({ onEnd }) => {
  return (
    <div className="interview-controls">
      <Button variant="danger" size="md" onClick={onEnd}>
        End Interview
      </Button>
    </div>
  );
};

export default InterviewControls;
