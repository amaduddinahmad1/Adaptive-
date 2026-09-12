import React from 'react';
import Button from '../common/Button';

const InterviewControls = ({ onEnd }) => {
  return (
    <div className="flex items-center">
      <Button variant="danger" size="sm" onClick={onEnd}>
        End Interview
      </Button>
    </div>
  );
};

export default InterviewControls;
