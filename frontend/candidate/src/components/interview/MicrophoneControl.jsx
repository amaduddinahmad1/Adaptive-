import React from 'react';
import { MIC_STATE } from '../../types/interview';
import './MicrophoneControl.css';

const MicrophoneControl = ({ state, onClick }) => {
  const getIcon = () => {
    switch(state) {
      case MIC_STATE.LISTENING: return '🎙️';
      case MIC_STATE.PROCESSING: return '⏳';
      case MIC_STATE.MUTED: return '🔇';
      default: return '🎤';
    }
  };

  const getLabel = () => {
    switch(state) {
      case MIC_STATE.LISTENING: return 'Listening...';
      case MIC_STATE.PROCESSING: return 'Processing...';
      case MIC_STATE.MUTED: return 'Muted';
      default: return 'Tap to speak';
    }
  };

  return (
    <div className="mic-control-container">
      <button 
        className={`mic-button mic-${state.toLowerCase()}`}
        onClick={onClick}
        disabled={state === MIC_STATE.PROCESSING}
      >
        <span className="mic-icon">{getIcon()}</span>
        {state === MIC_STATE.LISTENING && (
          <div className="mic-rings">
            <div className="ring ring-1"></div>
            <div className="ring ring-2"></div>
          </div>
        )}
      </button>
      <span className="mic-label">{getLabel()}</span>
    </div>
  );
};

export default MicrophoneControl;
