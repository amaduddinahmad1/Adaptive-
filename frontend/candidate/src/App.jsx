import React, { useState } from 'react';
import InstructionsPage from './pages/InstructionsPage';
import InterviewPage from './pages/InterviewPage';
import InterviewCompletedPage from './pages/InterviewCompletedPage';
import './App.css';

function App() {
  const [currentPage, setCurrentPage] = useState('instructions'); // instructions, interview, completed

  const navigateTo = (page) => {
    setCurrentPage(page);
  };

  return (
    <div className="app-container">
      {currentPage === 'instructions' && (
        <InstructionsPage onStart={() => navigateTo('interview')} />
      )}
      {currentPage === 'interview' && (
        <InterviewPage onComplete={() => navigateTo('completed')} />
      )}
      {currentPage === 'completed' && (
        <InterviewCompletedPage />
      )}
    </div>
  );
}

export default App;
