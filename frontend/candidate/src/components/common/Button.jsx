import React from 'react';

const baseClass =
  'inline-flex items-center justify-center gap-2 rounded-md font-sans font-medium cursor-pointer border border-transparent outline-none disabled:opacity-50 disabled:cursor-not-allowed transition-[color,background-color,border-color,transform,filter] duration-150 ease-out';

const variantClass = {
  primary:
    'bg-accent text-text shadow-sm hover:bg-accent/90 hover:scale-[1.02] hover:brightness-110 active:scale-[0.985] active:brightness-95 disabled:hover:bg-accent disabled:hover:scale-100 disabled:hover:brightness-100 disabled:active:scale-100',
  solid: 'bg-accent text-text shadow-sm hover:bg-accent/90 disabled:hover:bg-accent',
  secondary:
    'bg-transparent border-white/10 text-text hover:bg-white/5 disabled:hover:bg-transparent',
  ghost:
    'bg-transparent border-transparent text-text hover:bg-white/5 disabled:hover:bg-transparent',
  danger:
    'bg-red-500/10 border-red-500/20 text-red-400 hover:bg-red-500/20 disabled:hover:bg-red-500/10',
};

const sizeClass = {
  sm: 'px-3 py-2 text-sm',
  md: 'px-5 py-3 text-base',
  lg: 'px-6 py-4 text-lg',
};

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon,
  onClick,
  className = '',
  ...props
}) => {
  return (
    <button
      className={`${baseClass} ${variantClass[variant] ?? variantClass.primary} ${sizeClass[size] ?? sizeClass.md} ${className}`.trim()}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {loading && (
        <span
          className="inline-block size-[1em] rounded-full border-2 border-current border-r-transparent animate-spin"
          aria-hidden="true"
        />
      )}
      {!loading && icon && <span className="inline-flex">{icon}</span>}
      <span>{children}</span>
    </button>
  );
};

export default Button;
