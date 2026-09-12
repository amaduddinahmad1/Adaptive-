import React from 'react';
import { formatTime } from '../../utils/formatters';

const Timer = ({ seconds }) => {
  return (
    <div className="inline-flex items-center font-sans text-sm text-text-muted">
      <span className="font-mono tabular-nums">{formatTime(seconds)}</span>
    </div>
  );
};

export default Timer;
