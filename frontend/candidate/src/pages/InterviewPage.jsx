import React, { useCallback, useEffect, useRef } from 'react';
import InterviewHeader from '../components/interview/InterviewHeader';
import QuestionDisplay from '../components/interview/QuestionDisplay';
import TranscriptPanel from '../components/interview/TranscriptPanel';
import MicrophoneControl from '../components/interview/MicrophoneControl';
import ConnectionStatus from '../components/interview/ConnectionStatus';
import InterviewControls from '../components/interview/InterviewControls';
import LoadingSpinner from '../components/common/LoadingSpinner';
import Button from '../components/common/Button';
import AmbientSurface from '../components/common/AmbientSurface';
import { useInterview } from '../hooks/useInterview';
import { useFullscreenEnforcement } from '../hooks/useFullscreenEnforcement';
import { useViolationTracking } from '../hooks/useViolationTracking';
import { CONNECTION_STATUS, INTERVIEW_STATUS } from '../types/interview';

const preventCopy = (event) => {
  event.preventDefault();
};

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

  const interviewActive =
    status === INTERVIEW_STATUS.IN_PROGRESS || status === INTERVIEW_STATUS.PAUSED;

  const {
    violations,
    currentWarning,
    interviewTerminated,
    recordViolation,
    dismissWarning,
  } = useViolationTracking({ enabled: interviewActive });

  const endedForViolationsRef = useRef(false);

  const handleFullscreenExit = useCallback(() => {
    recordViolation('fullscreen_exit');
  }, [recordViolation]);

  const { isFullscreen, reenterFullscreen } = useFullscreenEnforcement({
    enabled: status !== INTERVIEW_STATUS.COMPLETED,
    onFullscreenExit: handleFullscreenExit,
  });

  useEffect(() => {
    // Automatically start the interview process when mounting
    actions.startInterview();
  }, []);

  useEffect(() => {
    const blockContextMenu = (event) => {
      event.preventDefault();
    };
    document.addEventListener('contextmenu', blockContextMenu);
    return () => document.removeEventListener('contextmenu', blockContextMenu);
  }, []);

  useEffect(() => {
    if (!interviewActive) return;

    const warnBeforeLeave = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', warnBeforeLeave);
    return () => window.removeEventListener('beforeunload', warnBeforeLeave);
  }, [interviewActive]);

  useEffect(() => {
    if (!interviewTerminated || endedForViolationsRef.current) return;
    endedForViolationsRef.current = true;
    actions.endInterview({ violations });
  }, [interviewTerminated, violations, actions]);

  // When status becomes completed, trigger the parent callback
  useEffect(() => {
    if (status === INTERVIEW_STATUS.COMPLETED) {
      onComplete();
    }
  }, [status, onComplete]);

  const warningPrompt = currentWarning ? (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/80 p-6">
      <div
        className="max-w-md rounded-lg border border-info/30 bg-surface p-6 text-center"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="violation-warning-title"
        aria-describedby="violation-warning-message"
      >
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-info">
          Integrity reminder
        </p>
        <h2
          id="violation-warning-title"
          className="mb-2 font-display text-lg font-semibold text-accent"
        >
          Please stay in the interview
        </h2>
        <p id="violation-warning-message" className="mb-5 text-sm text-text">
          {currentWarning}
        </p>
        <Button onClick={dismissWarning}>I understand</Button>
      </div>
    </div>
  ) : null;

  const fullscreenPrompt =
    !isFullscreen && status !== INTERVIEW_STATUS.COMPLETED ? (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-6">
        <div className="max-w-md rounded-lg border border-white/10 bg-surface p-6 text-center">
          <h2 className="mb-2 font-display text-lg font-semibold text-accent">
            Fullscreen required
          </h2>
          <p className="mb-5 text-sm text-text-muted">
            This interview must stay in fullscreen. Click below to return — leaving
            fullscreen is flagged.
          </p>
          <Button onClick={reenterFullscreen}>Return to fullscreen</Button>
        </div>
      </div>
    ) : null;

  if (status === INTERVIEW_STATUS.NOT_STARTED && connection !== CONNECTION_STATUS.FAILED) {
    return (
      <div className="relative z-0 flex h-screen flex-col items-center justify-center gap-4 bg-ink font-sans text-text-muted">
        {warningPrompt}
        {fullscreenPrompt}
        <LoadingSpinner size="lg" />
        <p className="text-sm">Connecting to AI Interviewer...</p>
      </div>
    );
  }

  return (
    <div className="relative z-0 flex h-screen flex-col overflow-hidden bg-ink font-sans text-text">
      {warningPrompt}
      {fullscreenPrompt}

      <InterviewHeader
        candidateName={candidateInfo.name}
        role={candidateInfo.role}
        status={status}
        elapsedTime={elapsedTime}
      />

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="relative isolate flex min-h-0 flex-1 flex-col px-8 py-10 sm:px-12 lg:px-16 lg:py-14 xl:px-24">
          <AmbientSurface variant="stage" />
          <div className="relative z-10 flex min-h-0 flex-1 select-none items-center" onCopy={preventCopy}>
            <QuestionDisplay
              key={currentQuestion?.id ?? currentQuestionNumber}
              question={currentQuestion}
              number={currentQuestionNumber}
              total={totalQuestions}
            />
          </div>
          <div className="relative z-10 flex shrink-0 justify-center pb-2 pt-10 lg:justify-start lg:pt-14">
            <MicrophoneControl state={micState} onClick={actions.toggleMic} />
          </div>
        </div>

        <div className="flex max-h-52 min-h-0 w-full shrink-0 select-none flex-col border-t border-white/5 lg:max-h-none lg:w-72 lg:border-l lg:border-t-0 xl:w-80" onCopy={preventCopy}>
          <TranscriptPanel transcript={transcript} />
        </div>
      </div>

      <div className="flex shrink-0 items-center justify-between px-8 py-3 sm:px-12 lg:px-16 xl:px-24">
        <div>
          <ConnectionStatus status={connection} onRetry={actions.retryConnection} />
        </div>
        <InterviewControls onEnd={actions.endInterview} />
      </div>
    </div>
  );
};

export default InterviewPage;
