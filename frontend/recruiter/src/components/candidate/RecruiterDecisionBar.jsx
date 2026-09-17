import { useState } from 'react';
import Button from '../common/Button';
import { api } from '../../services/api';

function isRejected(application) {
  return String(application?.hiring_decision || '').toLowerCase() === 'rejected';
}

export default function RecruiterDecisionBar({
  compact = false,
  application = null,
  onUpdated,
}) {
  const [note, setNote] = useState('');
  const [tone, setTone] = useState('info');
  const [submitting, setSubmitting] = useState(false);
  const rejected = isRejected(application);

  const announce = (action) => {
    setTone('info');
    setNote(`${action} is a recruiter decision and is not persisted by the backend.`);
  };

  const rejectCandidate = async () => {
    if (!application?.id || rejected || submitting) return;
    setSubmitting(true);
    setNote('');
    try {
      const updated = await api.submitApplicationDecision(application.id, 'rejected');
      setTone('success');
      setNote('Candidate rejected. The application and assessment remain available.');
      onUpdated?.(updated);
    } catch (err) {
      setTone('error');
      setNote(err?.message || 'Unable to reject this candidate. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`decision-bar${compact ? ' is-compact' : ''}`}>
      <Button variant="ghost" onClick={() => window.print()}>Export PDF Report</Button>
      <Button
        variant="danger"
        onClick={rejectCandidate}
        disabled={!application?.id || rejected || submitting}
      >
        {rejected ? 'Candidate Rejected' : submitting ? 'Rejecting…' : 'Reject Candidate'}
      </Button>
      <Button variant="secondary" onClick={() => announce('Schedule round 2')}>Schedule Round 2</Button>
      <Button onClick={() => announce('Approve / extend offer')}>Approve & Extend Offer</Button>
      {note ? <p className={`decision-note is-${tone}`}>{note}</p> : null}
    </div>
  );
}
