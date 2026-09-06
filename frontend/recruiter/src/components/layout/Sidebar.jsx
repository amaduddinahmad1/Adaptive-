import './Sidebar.css';
export default function Sidebar({ activeTab, onTabChange }) {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'jobs', label: 'Jobs', icon: '💼', badge: 'Soon' },
    { id: 'candidates', label: 'Candidates', icon: '👥', badge: 'Soon' },
    { id: 'reports', label: 'Reports', icon: '📈', badge: 'Soon' },
    { id: 'settings', label: 'Settings', icon: '⚙️', badge: 'Soon' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>InterviewAI</h2>
      </div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => onTabChange(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {item.badge && <span className="nav-badge">{item.badge}</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="user-info">
          <div className="avatar">R</div>
          <div className="user-details">
            <div className="user-name">Recruiter User</div>
            <div className="user-role">Admin</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
