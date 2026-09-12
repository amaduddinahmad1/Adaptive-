import React from 'react';

const isActive = (status) => status === 'online' || status === 'connected';

const StatusIndicator = ({ status, label }) => {
  const active = isActive(status);

  return (
    <div className="inline-flex items-center gap-2 font-sans">
      <span
        className={`size-2 rounded-full ${
          active
            ? 'bg-info'
            : status === 'connecting'
              ? 'bg-info/50'
              : 'bg-text-muted'
        }`}
      />
      {label && <span className="text-xs text-text-muted">{label}</span>}
    </div>
  );
};

export default StatusIndicator;
