import './TopBar.css';
export default function TopBar() {
  return (
    <header className="topbar">
      <div className="search-container">
        <input type="text" placeholder="Search candidates, jobs..." className="search-input" />
      </div>
      <div className="topbar-actions">
        <button className="action-btn">🔔</button>
      </div>
    </header>
  );
}
