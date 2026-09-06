import './EmptyState.css';
export default function EmptyState({ title, description, icon }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon || '✨'}</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-description">{description}</p>
    </div>
  );
}
