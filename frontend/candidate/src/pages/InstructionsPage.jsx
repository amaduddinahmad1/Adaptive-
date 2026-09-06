import React, { useState } from 'react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import './InstructionsPage.css';

const InstructionsPage = ({ onStart }) => {
  const [loading, setLoading] = useState(false);

  const handleStart = () => {
    setLoading(true);
    setTimeout(() => {
      onStart();
    }, 1000);
  };

  return (
    <div className="page-container instructions-page">
      <div className="instructions-content">
        <h1 className="instructions-title">Welcome to your AI Interview</h1>
        <p className="instructions-subtitle">
          Please review the instructions below before starting.
        </p>
        
        <Card className="instructions-card">
          <div className="instruction-section">
            <h3>How it works</h3>
            <ul>
              <li>You will be speaking with our AI interviewer.</li>
              <li>Ensure you are in a quiet room with a stable internet connection.</li>
              <li>Read the question carefully and press the microphone button to start answering.</li>
              <li>Speak clearly. The AI will process your response and move to the next question.</li>
            </ul>
          </div>
          
          <div className="instruction-section">
            <h3>System Check</h3>
            <div className="system-checks">
              <div className="check-item success">
                <span className="check-icon">✓</span> Microphone detected
              </div>
              <div className="check-item success">
                <span className="check-icon">✓</span> Speakers detected
              </div>
              <div className="check-item success">
                <span className="check-icon">✓</span> Connection stable
              </div>
            </div>
          </div>
          
          <div className="instructions-actions">
            <Button size="lg" loading={loading} onClick={handleStart}>
              Start Interview
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default InstructionsPage;
