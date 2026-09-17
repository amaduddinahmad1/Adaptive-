import './Card.css';

export default function Card({ children, className = '', title, action }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-head">
          {title ? <h3>{title}</h3> : <span />}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
