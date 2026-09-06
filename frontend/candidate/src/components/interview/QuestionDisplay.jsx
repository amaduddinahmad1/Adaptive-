import React from 'react';
import Card from '../common/Card';
import './QuestionDisplay.css';

const QuestionDisplay = ({ question, number, total }) => {
  if (!question) return null;

  return (
    <Card className="question-display" padded={false}>
      <div className="question-header">
        <span className="question-number">Question {number} of {total}</span>
      </div>
      <div className="question-body">
        <h3 className="question-text">{question.text}</h3>
      </div>
    </Card>
  );
};

export default QuestionDisplay;
