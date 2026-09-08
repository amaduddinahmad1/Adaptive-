import React, { useEffect } from 'react';
import InterviewHeader from '../components/interview/InterviewHeader';
import QuestionDisplay from '../components/interview/QuestionDisplay';
import TranscriptPanel from '../components/interview/TranscriptPanel';
import MicrophoneControl from '../components/interview/MicrophoneControl';
import ConnectionStatus from '../components/interview/ConnectionStatus';
import InterviewControls from '../components/interview/InterviewControls';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useInterview } from '../hooks/useInterview';
import { CONNECTION_STATUS, INTERVIEW_STATUS } from '../types/interview';
import './InterviewPage.css';

const InterviewPage = ({ onComplete }) => {
  const {
    status,
    connection,
    micState,
    candidateInfo,
    currentQuestion,
    currentQuestionNumber,
    totalQuestions,
    transcript,
    elapsedTime,
    actions
  } = useInterview();

  useEffect(() => {
    // Automatically start the interview process when mounting
    actions.startInterview();
  }, []);

  // When status becomes completed, trigger the parent callback
  useEffect(() => {
    if (status === INTERVIEW_STATUS.COMPLETED) {
      onComplete();
    }
  }, [status, onComplete]);

  if (status === INTERVIEW_STATUS.NOT_STARTED && connection !== CONNECTION_STATUS.FAILED) {
    return (
      <div className="loading-container">
        <LoadingSpinner size="lg" />
        <p>Connecting to AI Interviewer...</p>
      </div>
    );
  }

  return (
    <div className="interview-layout">
      <div className="interview-header-area">
        <InterviewHeader 
          candidateName={candidateInfo.name} 
          role={candidateInfo.role} 
          status={status}
          elapsedTime={elapsedTime}
        />
      </div>
      
      <div className="interview-main-area">
        <div className="interview-left-panel">
          <div className="question-area">
            <QuestionDisplay 
              question={currentQuestion} 
              number={currentQuestionNumber} 
              total={totalQuestions} 
            />
          </div>
          <div className="mic-area">
            <MicrophoneControl state={micState} onClick={actions.toggleMic} />
          </div>
        </div>
        
        <div className="interview-right-panel">
          <TranscriptPanel transcript={transcript} />
        </div>
      </div>
      
      <div className="interview-footer-area">
        <div className="status-container">
          <ConnectionStatus status={connection} onRetry={actions.retryConnection} />
        </div>
        <InterviewControls onEnd={actions.endInterview} />
      </div>
    </div>
  );
};

export default InterviewPage;
