import { useState, useEffect, useCallback, useRef } from 'react';
import { INTERVIEW_STATUS, CONNECTION_STATUS, MIC_STATE } from '../types/interview';
import * as service from '../services/interviewService';

export const useInterview = () => {
  const [status, setStatus] = useState(INTERVIEW_STATUS.NOT_STARTED);
  const [connection, setConnection] = useState(CONNECTION_STATUS.DISCONNECTED);
  const [micState, setMicState] = useState(MIC_STATE.INACTIVE);
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(0);
  const [questions, setQuestions] = useState([]);
  const [transcript, setTranscript] = useState([]);
  const [candidateInfo, setCandidateInfo] = useState({ name: '', role: '' });
  const [elapsedTime, setElapsedTime] = useState(0);
  
  const timerRef = useRef(null);

  useEffect(() => {
    // Initial fetch mock
    service.getSession('mock-123').then(data => {
      setCandidateInfo({ name: data.candidateName, role: data.role });
      setQuestions(data.questions);
    });
  }, []);

  const addTranscript = (sender, text) => {
    setTranscript(prev => [...prev, { id: Date.now(), sender, text, timestamp: new Date().toISOString() }]);
  };

  const handleStart = async () => {
    setConnection(CONNECTION_STATUS.CONNECTING);
    await service.startInterview('mock-123');
    setConnection(CONNECTION_STATUS.CONNECTED);
    setStatus(INTERVIEW_STATUS.IN_PROGRESS);
    
    // Start timer
    timerRef.current = setInterval(() => {
      setElapsedTime(prev => prev + 1);
    }, 1000);

    // Initial AI message
    if (questions.length > 0) {
      setTimeout(() => {
        addTranscript('AI', "Hello, thanks for joining. Let's get started. " + questions[0].text);
      }, 1000);
    }
  };

  const handleEnd = async () => {
    clearInterval(timerRef.current);
    await service.endInterview('mock-123');
    setStatus(INTERVIEW_STATUS.COMPLETED);
    setConnection(CONNECTION_STATUS.DISCONNECTED);
  };

  const toggleMic = () => {
    if (micState === MIC_STATE.INACTIVE) {
      setMicState(MIC_STATE.LISTENING);
    } else if (micState === MIC_STATE.LISTENING) {
      setMicState(MIC_STATE.PROCESSING);
      setTimeout(() => {
        addTranscript('Candidate', "This is a mock candidate response simulating speech recognition.");
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
      toggleMic
    }
  };
};
