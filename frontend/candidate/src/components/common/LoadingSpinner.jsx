import React from 'react';

const sizeClass = {
  sm: 'size-4',
  md: 'size-6',
  lg: 'size-12',
};

const LoadingSpinner = ({ size = 'md' }) => {
  return (
    <div className="flex items-center justify-center">
      <div
        className={`rounded-full border-2 border-white/10 border-t-accent animate-spin ${sizeClass[size] ?? sizeClass.md}`}
        role="status"
        aria-label="Loading"
      />
    </div>
  );
};

export default LoadingSpinner;
