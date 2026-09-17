export default function PageHeader({ title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-subtitle">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
