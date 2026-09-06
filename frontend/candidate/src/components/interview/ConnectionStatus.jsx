import React from 'react';
import StatusIndicator from '../common/StatusIndicator';
import { CONNECTION_STATUS } from '../../types/interview';
import './ConnectionStatus.css';

const ConnectionStatus = ({ status }) => {
  const getProps = () => {
    switch(status) {
      case CONNECTION_STATUS.CONNECTED: return { status: 'online', label: 'Connected', pulsing: false };
      case CONNECTION_STATUS.CONNECTING:
      case CONNECTION_STATUS.RECONNECTING: return { status: 'connecting', label: 'Connecting...', pulsing: true };
      case CONNECTION_STATUS.DISCONNECTED: return { status: 'offline', label: 'Disconnected', pulsing: false };
      default: return { status: 'offline', label: 'Offline', pulsing: false };
    }
  };

  return (
    <div className="connection-status">
      <StatusIndicator {...getProps()} />
    </div>
  );
};

export default ConnectionStatus;
