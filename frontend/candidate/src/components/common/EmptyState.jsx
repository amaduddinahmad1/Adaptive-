import React from 'react';
import './EmptyState.css';

const EmptyState = ({ icon, title, description }) => {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3 className="empty-title">{title}</h3>
      {description && <p className="empty-description">{description}</p>}
    </div>
  );
};

export default EmptyState;
