import './LoadingSpinner.css';

export default function LoadingSpinner({ label = 'Loading' }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <div className="spinner" />
      <span>{label}…</span>
    </div>
  );
}
