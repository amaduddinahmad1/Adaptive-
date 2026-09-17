import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { BrandMark, Icon } from '../common/Icons';
import './Sidebar.css';

function initialsFor(name, email) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (email || 'R').slice(0, 2).toUpperCase();
}

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'grid', end: true },
  { to: '/jobs', label: 'Job Postings', icon: 'briefcase' },
  { to: '/pipeline', label: 'Candidate Pipeline', icon: 'users' },
  { to: '/sessions', label: 'Live AI Sessions', icon: 'waveform' },
  { to: '/analytics', label: 'Analytics', icon: 'chart' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];

export default function Sidebar({ onNavigate }) {
  const navigate = useNavigate();
  const { recruiter, logout } = useAuth();
  const displayName = recruiter?.full_name || 'Recruiter';
  const displayEmail = recruiter?.email || '';
  const initials = initialsFor(displayName, displayEmail);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <BrandMark />
        <div>
          <div className="brand-name">InterviewAI</div>
          <div className="brand-tier">Enterprise Tier</div>
        </div>
      </div>

      <button
        type="button"
        className="sidebar-cta"
        onClick={() => {
          onNavigate?.();
          navigate('/jobs/new');
        }}
      >
        <Icon name="plus" size={16} />
        New Job Posting
      </button>

      <nav className="sidebar-nav">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            onClick={onNavigate}
          >
            <Icon name={item.icon} size={18} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button type="button" className="nav-item" disabled title="Support is not connected">
          <Icon name="help" size={18} />
          <span>Support</span>
        </button>
        <button
          type="button"
          className="nav-item"
          onClick={() => {
            onNavigate?.();
            logout();
          }}
        >
          <Icon name="logout" size={18} />
          <span>Sign Out</span>
        </button>
        <div className="user-chip">
          <div className="avatar">{initials}</div>
          <div>
            <div className="user-name">{displayName}</div>
            <div className="user-role">{displayEmail || 'Recruiter'}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
