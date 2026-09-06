import React from 'react';
import { formatTime } from '../../utils/formatters';
import './Timer.css';

const Timer = ({ seconds }) => {
  return (
    <div className="timer-display">
      <span className="timer-icon">⏱</span>
      <span className="timer-text">{formatTime(seconds)}</span>
    </div>
  );
};

export default Timer;
