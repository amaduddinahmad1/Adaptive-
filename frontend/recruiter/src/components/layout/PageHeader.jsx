import './PageHeader.css';
export default function PageHeader({ title, description, action }) {
  return (
    <div className="page-header">
      <div className="header-content">
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="header-action">{action}</div>}
    </div>
  );
}
