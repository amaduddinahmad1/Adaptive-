import React from 'react';
import './Card.css';

const Card = ({ children, className = '', padded = true, hover = false }) => {
  return (
    <div className={`card ${padded ? 'card-padded' : ''} ${hover ? 'card-hover' : ''} ${className}`}>
      {children}
    </div>
  );
};

export default Card;
