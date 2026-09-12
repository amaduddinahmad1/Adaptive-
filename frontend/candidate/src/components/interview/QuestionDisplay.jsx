import React from 'react';

const QuestionDisplay = ({ question, number, total }) => {
  if (!question) return null;

  return (
    <div className="animate-question-in w-full max-w-3xl">
      <p className="mb-5 font-sans text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
        Question {number} of {total}
      </p>
      <p className="font-display text-3xl font-medium leading-snug tracking-tight text-text md:text-4xl">
        {question.text}
      </p>
    </div>
  );
};

export default QuestionDisplay;
