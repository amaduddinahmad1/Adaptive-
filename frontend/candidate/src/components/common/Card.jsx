import React from 'react';

const Card = ({ children, className = '', padded = true, hover = false }) => {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-accent/10 bg-surface font-sans text-text-muted ${padded ? 'p-6' : ''} ${hover ? 'transition-[border-color,transform,filter] duration-150 ease-out hover:border-accent/20 hover:scale-[1.01] hover:brightness-110 active:scale-[1.005]' : ''} ${className}`.trim()}
    >
      {children}
    </div>
  );
};

export default Card;
