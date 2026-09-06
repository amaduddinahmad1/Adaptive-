import React from 'react';
import './StatusIndicator.css';

const StatusIndicator = ({ status, label, pulsing = false }) => {
  // status: 'online', 'offline', 'connecting'
  return (
    <div className="status-indicator">
      <span className={`status-dot status-${status} ${pulsing ? 'pulsing' : ''}`}></span>
      {label && <span className="status-label">{label}</span>}
    </div>
  );
};

export default StatusIndicator;
