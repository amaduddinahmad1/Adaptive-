import React, { useEffect, useRef } from 'react';

const TranscriptPanel = ({ transcript }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  return (
    <div className="flex h-full min-h-0 flex-col px-5 py-5 lg:px-6 lg:py-8">
      <p className="mb-4 font-sans text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
        Transcript
      </p>
      <div className="min-h-0 flex-1 overflow-y-auto" ref={scrollRef}>
        {transcript.length === 0 ? (
          <p className="font-sans text-xs leading-relaxed text-text-muted">
            The conversation will appear here.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {transcript.map(msg => (
              <div
                key={msg.id}
                className={`flex max-w-[92%] flex-col ${
                  msg.sender === 'AI' ? 'self-start' : 'self-end'
                }`}
              >
                <div
                  className={`mb-1 font-sans text-[10px] uppercase tracking-wide text-text-muted ${
                    msg.sender === 'AI' ? '' : 'text-right'
                  }`}
                >
                  {msg.sender}
                </div>
                <div className="font-sans text-xs leading-relaxed text-text-muted">
                  {msg.text}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TranscriptPanel;
