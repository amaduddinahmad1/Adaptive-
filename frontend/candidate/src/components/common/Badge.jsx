import React from 'react';

const variantClass = {
  success: 'bg-info/15 text-info',
  warning: 'bg-accent/15 text-accent',
  error: 'bg-red-500/15 text-red-400',
  info: 'bg-info/15 text-info',
  neutral: 'border border-white/10 bg-surface text-text-muted',
};

const Badge = ({ variant = 'neutral', children, dot = false }) => {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 font-sans text-xs font-semibold uppercase tracking-wide ${variantClass[variant] ?? variantClass.neutral}`}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
};

export default Badge;
