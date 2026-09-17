import './ProgressBar.css';

export default function ProgressBar({ value, label, tone = 'green' }) {
  const numeric = Number(value);
  const width = Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : 0;
  return (
    <div className="skill-bar">
      <div className="skill-bar-label">
        <span>{label}</span>
        <strong>{Number.isFinite(numeric) ? `${Math.round(numeric)}%` : '—'}</strong>
      </div>
      <div className="skill-bar-track">
        <div className={`skill-bar-fill tone-${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
