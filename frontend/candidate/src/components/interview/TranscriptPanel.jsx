import React, { useEffect, useRef } from 'react';
import Card from '../common/Card';
import EmptyState from '../common/EmptyState';
import './TranscriptPanel.css';

const TranscriptPanel = ({ transcript }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  return (
    <Card className="transcript-panel" padded={false}>
      <div className="transcript-header">
        <h4>Live Transcript</h4>
      </div>
      <div className="transcript-body" ref={scrollRef}>
        {transcript.length === 0 ? (
          <EmptyState icon="💬" title="No messages yet" description="The conversation transcript will appear here." />
        ) : (
          <div className="message-list">
            {transcript.map(msg => (
              <div key={msg.id} className={`message ${msg.sender === 'AI' ? 'message-ai' : 'message-candidate'}`}>
                <div className="message-sender">{msg.sender}</div>
                <div className="message-bubble">{msg.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
};

export default TranscriptPanel;
