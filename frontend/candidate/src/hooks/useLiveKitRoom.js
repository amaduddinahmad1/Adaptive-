import { useCallback, useEffect, useRef, useState } from 'react';
import { LiveKitSession } from '../services/livekitClient';

const CONNECTION_STATES = new Set([
  'disconnected',
  'connecting',
  'connected',
  'reconnecting',
  'failed',
]);

const normalizeConnectionState = (state) => {
  if (state === 'signalReconnecting') return 'reconnecting';
  if (CONNECTION_STATES.has(state)) return state;
  return 'disconnected';
};

export const useLiveKitRoom = () => {
  const sessionRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const [connectionState, setConnectionState] = useState('disconnected');
  const [error, setError] = useState(null);

  if (sessionRef.current === null) {
    sessionRef.current = new LiveKitSession();
  }

  useEffect(() => {
    const session = sessionRef.current;

    const audioEl = document.createElement('audio');
    audioEl.autoplay = true;
    audioEl.playsInline = true;
    audioEl.setAttribute('playsinline', '');
    audioEl.style.display = 'none';
    document.body.appendChild(audioEl);
    remoteAudioRef.current = audioEl;

    session.onConnectionStateChange((state) => {
      setConnectionState(normalizeConnectionState(state));
    });

    session.onRemoteAudioTrack((mediaStreamTrack) => {
      const el = remoteAudioRef.current;
      if (!el || !mediaStreamTrack) return;
      el.srcObject = new MediaStream([mediaStreamTrack]);
      el.play().catch(() => {});
    });

    const handleVisibility = () => {
      session.setMicrophoneEnabled(!document.hidden).catch(() => {});
    };

    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      session.onConnectionStateChange(null);
      session.onRemoteAudioTrack(null);
      session.onDisconnected(null);
      session.disconnect().catch(() => {});
      audioEl.srcObject = null;
      audioEl.remove();
      if (remoteAudioRef.current === audioEl) {
        remoteAudioRef.current = null;
      }
    };
  }, []);

  const connect = useCallback(async (livekitUrl, token) => {
    setConnectionState('connecting');
    try {
      await sessionRef.current.connect(livekitUrl, token);
      setError(null);
    } catch (err) {
      setError(err);
      setConnectionState('failed');
      throw err;
    }
  }, []);

  const disconnect = useCallback(async () => {
    await sessionRef.current.disconnect();
  }, []);

  return {
    connect,
    disconnect,
    connectionState,
    remoteAudioRef,
    error,
  };
};
