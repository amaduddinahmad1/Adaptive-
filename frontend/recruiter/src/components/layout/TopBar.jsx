import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Icon } from '../common/Icons';
import './TopBar.css';

function initialsFor(name, email) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (email || 'R').slice(0, 2).toUpperCase();
}

export default function TopBar({ onMenu, placeholder = 'Search candidates, jobs, or sessions...' }) {
  const navigate = useNavigate();
  const { recruiter } = useAuth();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const initials = initialsFor(recruiter?.full_name, recruiter?.email);

  const submit = (event) => {
    event.preventDefault();
    const next = query.trim();
    navigate(next ? `/pipeline?q=${encodeURIComponent(next)}` : '/pipeline');
  };

  return (
    <header className="topbar">
      <button type="button" className="icon-btn hidden-desktop" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" />
      </button>
      <form className="top-search" onSubmit={submit}>
        <Icon name="search" size={16} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
        />
      </form>
      <div className="topbar-actions">
        <button type="button" className="ghost-btn hidden-mobile" onClick={() => navigate('/jobs/new')}>
          <Icon name="plus" size={15} />
          Create New Job Posting
        </button>
        <button type="button" className="icon-btn" aria-label="Notifications" title="Notifications are not connected">
          <Icon name="bell" />
        </button>
        <div className="avatar" title={recruiter?.full_name || recruiter?.email || 'Recruiter'}>
          {initials}
        </div>
      </div>
    </header>
  );
}
