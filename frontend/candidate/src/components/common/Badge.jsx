import React from 'react';
import './Badge.css';

const Badge = ({ variant = 'neutral', children, dot = false }) => {
  return (
    <span className={`badge badge-${variant}`}>
      {dot && <span className="badge-dot"></span>}
      {children}
    </span>
  );
};

export default Badge;
