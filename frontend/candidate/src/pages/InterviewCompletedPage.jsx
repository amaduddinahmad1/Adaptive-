import React from 'react';
import Card from '../components/common/Card';
import './InterviewCompletedPage.css';

const InterviewCompletedPage = () => {
  return (
    <div className="page-container completed-page">
      <Card className="completed-card">
        <div className="completed-icon">🎉</div>
        <h1 className="completed-title">Interview Completed</h1>
        <p className="completed-message">
          Thank you for your time. Your responses have been recorded and will be analyzed by our system.
        </p>
        
        <div className="completed-details">
          <h3>What's Next?</h3>
          <p>
            The recruitment team will review your interview results and get back to you within 3-5 business days. 
            You can now close this window.
          </p>
        </div>
      </Card>
    </div>
  );
};

export default InterviewCompletedPage;
