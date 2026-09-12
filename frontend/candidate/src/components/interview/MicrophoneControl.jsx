import React from 'react';
import { MIC_STATE } from '../../types/interview';

const WAVEFORM_BARS = [14, 26, 18, 34, 22, 40, 16, 30, 24, 38, 12, 28, 20, 36, 18, 32];

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

  const isListening = state === MIC_STATE.LISTENING;
  const isProcessing = state === MIC_STATE.PROCESSING;
  const isActiveWave = isListening || isProcessing;

  return (
    <div className="flex flex-col items-center gap-4 lg:items-start">
      <div className="flex items-center gap-5">
        <div className="flex h-10 items-end gap-[3px]" aria-hidden="true">
          {WAVEFORM_BARS.map((height, index) => (
            <span
              key={index}
              className={`w-[2.5px] origin-bottom rounded-full ${
                isListening
                  ? 'animate-waveform bg-accent'
                  : isProcessing
                    ? 'animate-waveform-think bg-text-muted'
                    : 'bg-white/15'
              }`}
              style={{
                height: `${isActiveWave ? height : Math.max(5, Math.round(height * 0.22))}px`,
                animationDelay: isListening ? `${index * 70}ms` : '0ms',
              }}
            />
          ))}
        </div>
        <button
          type="button"
          className={`relative flex size-14 items-center justify-center rounded-full border font-sans text-xl transition-colors ${
            isListening
              ? 'border-accent/40 bg-accent/10 text-text'
              : 'border-white/10 bg-surface text-text-muted hover:border-white/20 hover:text-text'
          } ${isProcessing ? 'cursor-wait opacity-70' : 'cursor-pointer'}`}
          onClick={onClick}
          disabled={state === MIC_STATE.PROCESSING}
        >
          <span>{getIcon()}</span>
        </button>
      </div>
      <span className="font-sans text-xs text-text-muted">{getLabel()}</span>
    </div>
  );
};

export default MicrophoneControl;
