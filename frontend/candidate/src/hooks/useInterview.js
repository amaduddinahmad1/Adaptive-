import { useState, useEffect, useCallback, useRef } from 'react';
import { INTERVIEW_STATUS, CONNECTION_STATUS, MIC_STATE } from '../types/interview';
import * as service from '../services/interviewService';
import { useLiveKitRoom } from './useLiveKitRoom';

const MOCK_QUESTIONS = [
  { id: 1, text: "Tell me about a time you had to lead a project under tight deadlines." },
  { id: 2, text: "How do you handle disagreements with senior team members?" },
  { id: 3, text: "Describe a complex technical problem you solved recently." }
];

const DEFAULT_CANDIDATE_INFO = { name: 'Alex Doe', role: 'Senior Frontend Engineer' };

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

const getOrCreateCandidateId = () => {
  const fromUrl = readQueryParam(['candidate_id', 'candidate']);
  if (fromUrl) return fromUrl;

  const stored = sessionStorage.getItem('interview-candidate-id');
  if (stored) return stored;

  const id = crypto.randomUUID();
  sessionStorage.setItem('interview-candidate-id', id);
  return id;
};

const SHARED_SESSION_KEY = 'interview-shared-session-id';

const persistSessionInUrl = (sessionId) => {
  const url = new URL(window.location.href);
  url.searchParams.set('session', sessionId);
  window.history.replaceState({}, '', url);
};

const readSharedSessionId = () =>
  readQueryParam(['session', 'session_id']) || localStorage.getItem(SHARED_SESSION_KEY);

const persistSharedSessionId = (sessionId) => {
  localStorage.setItem(SHARED_SESSION_KEY, sessionId);
  persistSessionInUrl(sessionId);
};

export const useInterview = () => {
  const { connect, disconnect, connectionState } = useLiveKitRoom();
  const livekitCredsRef = useRef({ url: null, token: null });

  const [status, setStatus] = useState(INTERVIEW_STATUS.NOT_STARTED);
  const [connection, setConnection] = useState(CONNECTION_STATUS.DISCONNECTED);
  const [micState, setMicState] = useState(MIC_STATE.INACTIVE);
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(0);
  const questions = MOCK_QUESTIONS;
  const [transcript, setTranscript] = useState([]);
  const candidateInfo = DEFAULT_CANDIDATE_INFO;
  const [elapsedTime, setElapsedTime] = useState(0);

  const timerRef = useRef(null);
  const sessionIdRef = useRef(readSharedSessionId());
  const startingRef = useRef(false);
  const candidateIdRef = useRef(getOrCreateCandidateId());
  const jobIdRef = useRef(readQueryParam(['job_id']) || 'demo-job');
  const languageRef = useRef(readQueryParam(['language']) || 'en');
  const hadLiveConnectionRef = useRef(false);
  const serverEndedRef = useRef(false);

  useEffect(() => {
    setConnection(
      LIVEKIT_TO_CONNECTION_STATUS[connectionState] ?? CONNECTION_STATUS.DISCONNECTED,
    );
  }, [connectionState]);

  // Server-initiated room drop (e.g. silence timeout). Not a retryable 'failed'.
  useEffect(() => {
    if (connectionState === 'connected') {
      hadLiveConnectionRef.current = true;
      return;
    }

    if (connectionState !== 'disconnected') return;
    if (status !== INTERVIEW_STATUS.IN_PROGRESS) return;
    if (!hadLiveConnectionRef.current) return;
    if (serverEndedRef.current) return;

    serverEndedRef.current = true;
    clearInterval(timerRef.current);
    localStorage.removeItem(SHARED_SESSION_KEY);
    setStatus(INTERVIEW_STATUS.COMPLETED);
  }, [connectionState, status]);

  const addTranscript = (sender, text) => {
    setTranscript(prev => [...prev, { id: Date.now(), sender, text, timestamp: new Date().toISOString() }]);
  };

  const ensureSession = useCallback(async () => {
    if (sessionIdRef.current) {
      try {
        await service.getSession(sessionIdRef.current);
        return sessionIdRef.current;
      } catch {
        sessionIdRef.current = null;
      }
    }

    const created = await service.createSession(
      candidateIdRef.current,
      jobIdRef.current,
      languageRef.current,
    );
    sessionIdRef.current = created.session_id;
    persistSharedSessionId(created.session_id);
    return created.session_id;
  }, []);

  const handleStart = async () => {
    if (startingRef.current) return;
    startingRef.current = true;

    setConnection(CONNECTION_STATUS.CONNECTING);

    try {
      const sessionId = await ensureSession();
      const candidateOverride = readQueryParam(['candidate']);
      const startResult = await service.startInterview(
        sessionId,
        candidateOverride || undefined,
      );

      livekitCredsRef.current = {
        url: startResult.livekit_url,
        token: startResult.token,
      };
      setStatus(INTERVIEW_STATUS.IN_PROGRESS);
      await connect(startResult.livekit_url, startResult.token);

      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);

      if (questions.length > 0) {
        setTimeout(() => {
          addTranscript('AI', "Hello, thanks for joining. Let's get started. " + questions[0].text);
        }, 1000);
      }
    } catch (err) {
      startingRef.current = false;
      setConnection(CONNECTION_STATUS.FAILED);
      console.error('Failed to start interview', err);
    }
  };

  const retryConnection = useCallback(async () => {
    const { url, token } = livekitCredsRef.current;
    if (!url || !token) {
      startingRef.current = false;
      await handleStart();
      return;
    }

    try {
      await connect(url, token);
    } catch (err) {
      console.error('Failed to reconnect to LiveKit', err);
    }
  }, [connect]);

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
      localStorage.removeItem(SHARED_SESSION_KEY);
      setStatus(INTERVIEW_STATUS.COMPLETED);
    }
  }, [disconnect]);

  const toggleMic = () => {
    if (micState === MIC_STATE.INACTIVE) {
      setMicState(MIC_STATE.LISTENING);
    } else if (micState === MIC_STATE.LISTENING) {
      setMicState(MIC_STATE.PROCESSING);
      setTimeout(() => {
        // TODO Day 3: wire real STT transcript here
        setMicState(MIC_STATE.INACTIVE);

        // Move to next question after processing
        if (currentQuestionIdx < questions.length - 1) {
          setTimeout(() => {
            const nextIdx = currentQuestionIdx + 1;
            setCurrentQuestionIdx(nextIdx);
            addTranscript('AI', "Great. Next question: " + questions[nextIdx].text);
          }, 1500);
        } else {
          setTimeout(() => {
            addTranscript('AI', "Thank you, that concludes our questions.");
            setTimeout(() => {
              handleEnd();
            }, 3000);
          }, 1500);
        }
      }, 2000);
    }
  };

  return {
    status,
    connection,
    micState,
    candidateInfo,
    currentQuestion: questions[currentQuestionIdx],
    currentQuestionNumber: currentQuestionIdx + 1,
    totalQuestions: questions.length,
    transcript,
    elapsedTime,
    actions: {
      startInterview: handleStart,
      endInterview: handleEnd,
      retryConnection,
      toggleMic
    }
  };
};
