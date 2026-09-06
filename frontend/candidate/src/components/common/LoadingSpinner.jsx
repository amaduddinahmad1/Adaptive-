import React from 'react';
import './LoadingSpinner.css';

const LoadingSpinner = ({ size = 'md' }) => {
  return (
    <div className={`spinner-container spinner-${size}`}>
      <div className="spinner-circle"></div>
    </div>
  );
};

export default LoadingSpinner;
