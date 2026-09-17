import Button from './Button';
import './Alert.css';

export default function ErrorState({ title = 'Unable to load', message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <h3>{title}</h3>
      <p>{message || 'The request to the backend failed.'}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
