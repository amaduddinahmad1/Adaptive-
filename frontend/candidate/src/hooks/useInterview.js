import { useState, useEffect, useCallback, useRef } from 'react';
import { INTERVIEW_STATUS, CONNECTION_STATUS, MIC_STATE } from '../types/interview';
import * as service from '../services/interviewService';
import { useLiveKitRoom } from './useLiveKitRoom';
import {
  nextMicMuteState,
  shouldCallEndOnLiveKitDisconnect,
  shouldEndInterviewFromMicToggle,
} from '../interview/turnControl';

const DEFAULT_CANDIDATE_INFO = { name: 'Alex Doe', role: 'Senior Frontend Engineer' };
const SESSION_POLL_MS = 2500;

const LIVEKIT_TO_CONNECTION_STATUS = {
  disconnected: CONNECTION_STATUS.DISCONNECTED,
  connecting: CONNECTION_STATUS.CONNECTING,
  connected: CONNECTION_STATUS.CONNECTED,
  reconnecting: CONNECTION_STATUS.RECONNECTING,
  failed: CONNECTION_STATUS.FAILED,
};

const readQueryParam = (names) => {
  const params = new URLSearchParams(window.location.search);
  for (const name of names) {
    const value = params.get(name);
    if (value) return value;
  }
  return null;
};

const sessionStorageKey = (applicationId) =>
  `interview-shared-session-id:${applicationId}`;

const persistSessionInUrl = (sessionId) => {
  const url = new URL(window.location.href);
  url.searchParams.set('session', sessionId);
  window.history.replaceState({}, '', url);
};

const readSharedSessionId = (applicationId) =>
  readQueryParam(['session', 'session_id']) ||
  (applicationId ? localStorage.getItem(sessionStorageKey(applicationId)) : null);

const persistSharedSessionId = (applicationId, sessionId) => {
  if (applicationId) {
    localStorage.setItem(sessionStorageKey(applicationId), sessionId);
  }
  persistSessionInUrl(sessionId);
};

export const useInterview = ({
  applicationId,
  candidateName,
  jobTitle,
} = {}) => {
  const { connect, disconnect, setMicrophoneEnabled, connectionState, disconnectReason } = useLiveKitRoom();
  const livekitCredsRef = useRef({ url: null, token: null });

  const [status, setStatus] = useState(INTERVIEW_STATUS.NOT_STARTED);
  const [micMuted, setMicMuted] = useState(false);
  const [currentQuestionText, setCurrentQuestionText] = useState(null);
  const [currentQuestionNumber, setCurrentQuestionNumber] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const candidateInfo = {
    name: candidateName || DEFAULT_CANDIDATE_INFO.name,
    role: jobTitle || DEFAULT_CANDIDATE_INFO.role,
  };
  const [elapsedTime, setElapsedTime] = useState(0);
  const [startError, setStartError] = useState(null);
  const [totalQuestions, setTotalQuestions] = useState(null);

  const timerRef = useRef(null);
  const sessionIdRef = useRef(readSharedSessionId(applicationId));
  const startingRef = useRef(false);
  const applicationIdRef = useRef(applicationId);
  const languageRef = useRef(readQueryParam(['language']) || 'en');
  const hadLiveConnectionRef = useRef(false);
  const serverEndedRef = useRef(false);
  const lastQuestionTextRef = useRef(null);
  const questionNumberRef = useRef(0);
  const micInteractionCountRef = useRef(0);

  const connection = startError
    ? CONNECTION_STATUS.FAILED
    : (LIVEKIT_TO_CONNECTION_STATUS[connectionState] ?? CONNECTION_STATUS.DISCONNECTED);

  const micState = micMuted
    ? MIC_STATE.MUTED
    : (connectionState === 'connected' ? MIC_STATE.LISTENING : MIC_STATE.INACTIVE);

  useEffect(() => {
    applicationIdRef.current = applicationId;
    sessionIdRef.current = readSharedSessionId(applicationId);
  }, [applicationId]);

  useEffect(() => {
    if (connectionState !== 'connected' || micMuted) return undefined;
    setMicrophoneEnabled(true).catch(() => {});
    return undefined;
  }, [connectionState, micMuted, setMicrophoneEnabled]);

  const addTranscript = (sender, text) => {
    setTranscript(prev => [...prev, { id: Date.now(), sender, text, timestamp: new Date().toISOString() }]);
  };

  const applyLiveQuestion = useCallback((questionText) => {
    const nextText = (questionText || '').trim() || null;
    if (!nextText) {
      setCurrentQuestionText(null);
      return;
    }
    if (lastQuestionTextRef.current === nextText) {
      setCurrentQuestionText(nextText);
      return;
    }
    lastQuestionTextRef.current = nextText;
    questionNumberRef.current += 1;
    setCurrentQuestionNumber(questionNumberRef.current);
    setCurrentQuestionText(nextText);
    addTranscript('AI', nextText);
  }, []);

  const refreshLiveQuestion = useCallback(async () => {
    if (!sessionIdRef.current) return;
    try {
      const details = await service.getSessionDetails(sessionIdRef.current);
      applyLiveQuestion(details?.current_question);
      const budget = details?.question_turn_budget;
      if (typeof budget === 'number' && budget > 0) {
        setTotalQuestions(budget);
      }
    } catch {
      // Session details are best-effort UI state; the LiveKit session remains authoritative.
    }
  }, [applyLiveQuestion]);

  const ensureSession = useCallback(async () => {
    const linkedApplicationId = applicationIdRef.current;
    if (!linkedApplicationId) {
      throw new Error('This interview invitation is invalid.');
    }

    if (sessionIdRef.current) {
      try {
        await service.getSession(sessionIdRef.current);
        return sessionIdRef.current;
      } catch {
        sessionIdRef.current = null;
      }
    }

    const created = await service.createSession(
      linkedApplicationId,
      languageRef.current,
    );
    sessionIdRef.current = created.session_id;
    persistSharedSessionId(linkedApplicationId, created.session_id);
    return created.session_id;
  }, []);

  const handleEnd = useCallback(async (extra) => {
    clearInterval(timerRef.current);
    serverEndedRef.current = true;
    const payload =
      extra && typeof extra === 'object' && !('nativeEvent' in extra)
        ? extra
        : undefined;
    try {
      if (sessionIdRef.current) {
        await service.endInterview(sessionIdRef.current, payload);
      }
    } catch (err) {
      console.error('Failed to end interview', err);
    } finally {
      await disconnect();
      if (applicationIdRef.current) {
        localStorage.removeItem(sessionStorageKey(applicationIdRef.current));
      }
      setStatus(INTERVIEW_STATUS.COMPLETED);
    }
  }, [disconnect]);

  // Persist only after LiveKit reports ROOM_DELETED (backend already tore
  // the room down). Reconnect/signal loss must not POST /end — that deletes
  // the room during interview startup.
  useEffect(() => {
    if (connectionState === 'connected') {
      hadLiveConnectionRef.current = true;
    }

    if (
      !shouldCallEndOnLiveKitDisconnect({
        connectionState,
        disconnectReason,
        interviewStatus: status,
        hadLiveConnection: hadLiveConnectionRef.current,
        alreadyEnding: serverEndedRef.current,
      })
    ) {
      return;
    }

    handleEnd();
  }, [connectionState, disconnectReason, status, handleEnd]);

  useEffect(() => {
    if (status !== INTERVIEW_STATUS.IN_PROGRESS) return undefined;
    refreshLiveQuestion();
    const timer = setInterval(refreshLiveQuestion, SESSION_POLL_MS);
    return () => clearInterval(timer);
  }, [status, refreshLiveQuestion]);

  const handleStart = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;

    setStartError(null);

    try {
      const sessionId = await ensureSession();
      const startResult = await service.startInterview(sessionId);

      livekitCredsRef.current = {
        url: startResult.livekit_url,
        token: startResult.token,
      };
      setStartError(null);
      setMicMuted(false);
      setStatus(INTERVIEW_STATUS.IN_PROGRESS);
      await connect(startResult.livekit_url, startResult.token);
      await setMicrophoneEnabled(true);

      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);

      await refreshLiveQuestion();
    } catch (err) {
      startingRef.current = false;
      setStartError(
        err?.message || 'The interview session is unavailable right now. Please try again.',
      );
      console.error('Failed to start interview', err);
    }
  }, [connect, ensureSession, refreshLiveQuestion, setMicrophoneEnabled]);

  const retryConnection = useCallback(async () => {
    const { url, token } = livekitCredsRef.current;
    if (!url || !token) {
      startingRef.current = false;
      await handleStart();
      return;
    }

    try {
      setMicMuted(false);
      await connect(url, token);
      await setMicrophoneEnabled(true);
    } catch (err) {
      console.error('Failed to reconnect to LiveKit', err);
    }
  }, [connect, handleStart, setMicrophoneEnabled]);

  const toggleMic = async () => {
    micInteractionCountRef.current += 1;
    if (shouldEndInterviewFromMicToggle(micInteractionCountRef.current)) {
      return;
    }
    const nextState = nextMicMuteState(micState, MIC_STATE);
    const nextMuted = nextState === MIC_STATE.MUTED;
    try {
      await setMicrophoneEnabled(!nextMuted);
      setMicMuted(nextMuted);
    } catch (err) {
      console.error('Failed to toggle microphone', err);
    }
  };

  return {
    status,
    connection,
    micState,
    candidateInfo,
    currentQuestion: currentQuestionText ? { text: currentQuestionText } : null,
    currentQuestionNumber,
    totalQuestions,
    transcript,
    elapsedTime,
    startError,
    actions: {
      startInterview: handleStart,
      endInterview: handleEnd,
      retryConnection,
      toggleMic
    }
  };
};
