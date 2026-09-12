import React from 'react';
import Card from '../components/common/Card';
import AmbientSurface from '../components/common/AmbientSurface';

const InterviewCompletedPage = () => {
  return (
    <div className="relative isolate flex min-h-screen flex-1 flex-col items-center justify-center bg-ink px-8 py-16 font-sans text-text sm:px-12 lg:px-16 xl:px-24">
      <div className="relative w-full max-w-xl">
        <AmbientSurface variant="heading" />
        <div className="relative z-10">
          <div className="animate-page-enter">
            <p className="mb-5 font-sans text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
              Session complete
            </p>
            <h1 className="font-display text-4xl font-semibold leading-[1.15] tracking-tight text-text md:text-5xl">
              Interview Completed
            </h1>
          </div>
          <div className="animate-page-enter-delayed">
            <p className="mt-6 text-base leading-relaxed text-text-muted md:text-lg">
              Thank you for your time. Your responses have been recorded and will be analyzed by our system.
            </p>

            <Card className="mt-12">
              <h2 className="mb-3 font-sans text-sm font-medium text-text">What's Next?</h2>
              <p className="text-sm leading-relaxed text-text-muted">
                The recruitment team will review your interview results and get back to you within 3-5 business days.
                You can now close this window.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InterviewCompletedPage;
