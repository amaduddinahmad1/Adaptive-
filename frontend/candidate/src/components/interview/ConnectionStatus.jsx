import React from 'react';
import StatusIndicator from '../common/StatusIndicator';
import Button from '../common/Button';
import { CONNECTION_STATUS } from '../../types/interview';
import './ConnectionStatus.css';

const STATUS_PROPS = {
  [CONNECTION_STATUS.CONNECTED]: { status: 'online', label: 'Connected', pulsing: false },
  [CONNECTION_STATUS.CONNECTING]: { status: 'connecting', label: 'Connecting...', pulsing: true },
  [CONNECTION_STATUS.RECONNECTING]: { status: 'connecting', label: 'Reconnecting...', pulsing: true },
  [CONNECTION_STATUS.DISCONNECTED]: { status: 'offline', label: 'Disconnected', pulsing: false },
  [CONNECTION_STATUS.FAILED]: { status: 'offline', label: 'Connection failed', pulsing: false },
};

const ConnectionStatus = ({ status, onRetry }) => {
  const indicator = STATUS_PROPS[status] ?? {
    status: 'offline',
    label: 'Offline',
    pulsing: false,
  };
  const showRetry = status === CONNECTION_STATUS.FAILED && typeof onRetry === 'function';
  const stateClass = String(status || 'offline').toLowerCase();

  return (
    <div className={`connection-status connection-status--${stateClass}`}>
      <StatusIndicator {...indicator} />
      {showRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
};

export default ConnectionStatus;
