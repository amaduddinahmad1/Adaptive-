import React, { useState } from 'react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import AmbientSurface from '../components/common/AmbientSurface';

const InstructionsPage = ({ onStart }) => {
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    // Fullscreen must be requested from this click — browsers require a user gesture.
    try {
      const root = document.documentElement;
      if (!document.fullscreenElement && !document.webkitFullscreenElement) {
        if (root.requestFullscreen) {
          await root.requestFullscreen();
        } else if (root.webkitRequestFullscreen) {
          root.webkitRequestFullscreen();
        }
      }
    } catch {
      // Continue even if the browser denies fullscreen; InterviewPage will detect and allow re-entry.
    }
    onStart();
  };

  return (
    <div className="relative isolate flex min-h-screen flex-1 flex-col items-center justify-center bg-ink px-8 py-16 font-sans text-text sm:px-12 lg:px-16 xl:px-24">
      <div className="relative w-full max-w-xl">
        <AmbientSurface variant="heading" />
        <div className="relative z-10">
          <h1 className="animate-page-enter font-display text-4xl font-semibold leading-[1.15] tracking-tight text-text md:text-5xl">
            Welcome to your AI Interview
          </h1>
          <div className="animate-page-enter-delayed">
            <p className="mt-4 text-base text-text-muted">
              Please review the instructions below before starting.
            </p>

            <div className="mt-12 flex flex-col gap-4">
              <Card>
                <h2 className="mb-4 font-sans text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                  How it works
                </h2>
                <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed text-text-muted">
                  <li>You will be speaking with our AI interviewer.</li>
                  <li>Ensure you are in a quiet room with a stable internet connection.</li>
                  <li>After you start, your microphone stays on. Wait for the interviewer to finish, then answer naturally — you do not need to tap the microphone for each question.</li>
                  <li>Speak clearly. The interviewer will detect when you have finished and continue automatically. Use mute only if you need to, and End Interview when you want to stop.</li>
                </ul>
              </Card>

              <Card>
                <h2 className="mb-4 font-sans text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                  System Check
                </h2>
                <div className="flex flex-col gap-2 text-sm text-text-muted">
                  <div className="flex items-center gap-3">
                    <span aria-hidden="true">✓</span> Microphone detected
                  </div>
                  <div className="flex items-center gap-3">
                    <span aria-hidden="true">✓</span> Speakers detected
                  </div>
                  <div className="flex items-center gap-3">
                    <span aria-hidden="true">✓</span> Connection stable
                  </div>
                </div>
              </Card>

              <div className="rounded-lg border border-info/30 bg-info/10 p-4">
                <h3 className="mb-2 font-display text-base font-semibold text-accent">
                  Fullscreen required
                </h3>
                <p className="text-sm text-text">
                  This interview must be taken in fullscreen mode. Starting will switch your
                  browser to fullscreen. Leaving fullscreen for any reason (including Escape)
                  will be flagged as a potential integrity violation.
                </p>
                <p className="mt-2 text-sm text-text-muted">
                  Stay in fullscreen until the interview ends. You will be asked to return if
                  you exit.
                </p>
              </div>
            </div>

            <div className="mt-10 flex justify-start">
              <Button size="lg" loading={loading} onClick={handleStart}>
                Start Interview
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InstructionsPage;
