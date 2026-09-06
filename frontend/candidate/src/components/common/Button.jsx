import React from 'react';
import './Button.css';

const Button = ({ 
  children, 
  variant = 'primary', // primary, secondary, ghost, danger
  size = 'md', // sm, md, lg
  loading = false,
  disabled = false,
  icon,
  onClick,
  ...props 
}) => {
  return (
    <button 
      className={`btn btn-${variant} btn-${size} ${loading ? 'btn-loading' : ''}`}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {loading && <span className="btn-spinner"></span>}
      {!loading && icon && <span className="btn-icon">{icon}</span>}
      <span className="btn-text">{children}</span>
    </button>
  );
};

export default Button;
