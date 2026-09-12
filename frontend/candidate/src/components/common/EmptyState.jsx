import React from 'react';

const EmptyState = ({ icon, title, description }) => {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center font-sans text-text-muted">
      {icon && <div className="mb-4 text-4xl opacity-50">{icon}</div>}
      <h3 className="mb-2 text-lg font-medium text-text-muted">{title}</h3>
      {description && <p className="max-w-[300px] text-sm">{description}</p>}
    </div>
  );
};

export default EmptyState;
