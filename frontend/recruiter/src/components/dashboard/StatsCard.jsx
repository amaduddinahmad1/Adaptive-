import './StatsCard.css';

export default function StatsCard({ title, value, hint, icon, empty }) {
  return (
    <article className={`metric-card${empty ? ' is-empty' : ''}`}>
      <div className="metric-top">
        <span className="eyebrow">{title}</span>
        {icon ? <span className="metric-icon">{icon}</span> : null}
      </div>
      {empty ? (
        <div className="metric-empty">No backend data</div>
      ) : (
        <div className="metric-value">{value}</div>
      )}
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </article>
  );
}
