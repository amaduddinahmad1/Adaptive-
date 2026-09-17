import './Input.css';

export default function Input({
  label,
  hint,
  as = 'input',
  className = '',
  ...props
}) {
  const Control = as;
  return (
    <label className={`field ${className}`}>
      {label ? <span className="eyebrow">{label}</span> : null}
      <Control className={as === 'textarea' ? 'control textarea' : 'control'} {...props} />
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}
