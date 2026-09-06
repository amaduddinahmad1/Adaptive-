import './StatsCard.css';
export default function StatsCard({ title, value, trend, icon }) {
  return (
    <div className="stats-card">
      <div className="stats-info">
        <div className="stats-title">{title}</div>
        <div className="stats-value">{value}</div>
        <div className={`stats-trend ${trend >= 0 ? 'positive' : 'negative'}`}>
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}% from last month
        </div>
      </div>
      <div className="stats-icon">{icon}</div>
    </div>
  );
}
