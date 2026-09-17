import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Badge from '../common/Badge';
import Button from '../common/Button';
import EmptyState from '../common/EmptyState';
import LoadingSpinner from '../common/LoadingSpinner';
import Modal from '../common/Modal';
import ProgressBar from '../common/ProgressBar';
import { api } from '../../services/api';
import { recommendationTone } from '../../utils/eligibility';
import { asNumber, formatPercent, initials } from '../../utils/formatters';
import './EvaluationModal.css';

function transcriptTurns(result) {
  const turns = result?.qa_transcript?.turns;
  return Array.isArray(turns) ? turns : [];
}

function skillScores(result) {
  const scores = result?.final_report?.skill_scores;
  return Array.isArray(scores) ? scores : [];
}

export default function EvaluationModal({ application, open, onClose }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open || !application?.id) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setResult(null);
    api
      .getInterviewResult(application.id)
      .then((payload) => {
        if (!cancelled) setResult(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, application?.id]);

  const turns = transcriptTurns(result).filter((turn) => {
    if (!query.trim()) return true;
    const blob = `${turn.question || ''} ${turn.answer || ''}`.toLowerCase();
    return blob.includes(query.trim().toLowerCase());
  });
  const skills = skillScores(result);
  const report = result?.final_report || {};

  return (
    <Modal
      open={open}
      wide
      onClose={onClose}
      title={application?.candidate_full_name || 'Candidate evaluation'}
      subtitle={application?.job_title}
    >
      <div className="eval-modal">
        <div className="eval-hero">
          <span className="avatar lg">{initials(application?.candidate_full_name)}</span>
          <div>
            <h3>{application?.candidate_full_name}</h3>
            <p>{application?.job_title}</p>
          </div>
          <div className="eval-hero-meta">
            <Badge variant={application?.overall_eligible ? 'pass' : 'fail'}>
              {application?.overall_eligible ? 'Eligible' : 'Not eligible'}
            </Badge>
            {result ? (
              <Badge variant={recommendationTone(result.recommendation)}>
                {result.recommendation}
              </Badge>
            ) : null}
            {application?.hiring_decision === 'rejected' ? (
              <Badge variant="fail">Rejected</Badge>
            ) : null}
          </div>
        </div>

        {loading ? <LoadingSpinner label="Loading evaluation" /> : null}
        {error && !result ? (
          <EmptyState
            title="Interview report unavailable"
            description={error.message || 'This application does not have a persisted InterviewResult yet.'}
          />
        ) : null}

        {result ? (
          <>
            <section className="eval-block">
              <div className="eval-block-head">
                <h4>Interview transcript</h4>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search transcript..."
                />
              </div>
              {turns.length ? (
                <div className="transcript-list">
                  {turns.map((turn, index) => (
                    <article key={`${turn.question}-${index}`} className="transcript-turn">
                      <p className="q">{turn.question}</p>
                      <p className="a">{turn.answer}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted">No transcript turns are stored for this interview.</p>
              )}
            </section>

            <div className="eval-grid">
              <section className="eval-block">
                <h4>Technical skills</h4>
                {skills.length ? (
                  skills.map((skill) => (
                    <ProgressBar
                      key={skill.skill_name}
                      label={skill.skill_name}
                      value={asNumber(skill.proficiency_score)}
                      tone={asNumber(skill.proficiency_score) >= 75 ? 'green' : 'lavender'}
                    />
                  ))
                ) : (
                  <p className="muted">No skill scores in the final report.</p>
                )}
              </section>
              <section className="eval-block">
                <h4>Soft skills</h4>
                <p>Problem solving: {formatPercent(result.problem_solving_performance)}</p>
                <p>Communication: {formatPercent(result.communication_performance)}</p>
              </section>
              <section className="eval-block">
                <h4>AI evaluation</h4>
                <p><strong>Recommendation:</strong> {result.recommendation}</p>
                <p><strong>Interview eligibility:</strong> {result.interview_eligibility_result}</p>
                {report.recommendation_reason ? <p>{report.recommendation_reason}</p> : null}
                {(report.strengths || []).length ? (
                  <ul>
                    {(report.strengths || []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </section>
            </div>
          </>
        ) : null}

        {!result && !loading && application ? (
          <section className="eval-block">
            <h4>Screening snapshot</h4>
            <p className="muted">
              Eligibility: {application.overall_eligible ? 'Eligible' : 'Not eligible'}. Invitation
              {' '}{application.email_sent_at ? 'sent' : 'not recorded as sent'}.
            </p>
          </section>
        ) : null}

        <div className="eval-actions">
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {application ? (
            <Link to={`/pipeline/${application.id}`}>
              <Button>Open full record</Button>
            </Link>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
