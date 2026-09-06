import './RecentActivity.css';
import Card from '../common/Card';
export default function RecentActivity() {
  const activities = [
    { text: 'Sarah Connor completed interview', time: '2 mins ago', icon: '✅' },
    { text: 'New application for Frontend Engineer', time: '1 hour ago', icon: '📄' },
    { text: 'AI Assessment report generated for John', time: '3 hours ago', icon: '🤖' },
  ];
  return (
    <Card className="activity-card">
      <h3 className="card-title">Recent Activity</h3>
      <div className="activity-list">
        {activities.map((act, i) => (
          <div key={i} className="activity-item">
            <div className="activity-icon">{act.icon}</div>
            <div className="activity-details">
              <div className="activity-text">{act.text}</div>
              <div className="activity-time">{act.time}</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
