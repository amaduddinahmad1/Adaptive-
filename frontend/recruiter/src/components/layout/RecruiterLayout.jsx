import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function RecruiterLayout() {
  const [open, setOpen] = useState(false);

  return (
    <div className={`app-shell${open ? ' sidebar-open' : ''}`}>
      {open ? <div className="sidebar-backdrop" onClick={() => setOpen(false)} /> : null}
      <Sidebar onNavigate={() => setOpen(false)} />
      <div className="main-column">
        <TopBar onMenu={() => setOpen(true)} />
        <div className="page-scroll">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
