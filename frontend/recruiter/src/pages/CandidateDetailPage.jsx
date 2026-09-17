import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ErrorState from '../components/common/Alert';
import Badge from '../components/common/Badge';
import Card from '../components/common/Card';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ProgressBar from '../components/common/ProgressBar';
import RecruiterDecisionBar from '../components/candidate/RecruiterDecisionBar';
import EvaluationModal from '../components/candidate/EvaluationModal';
import { api } from '../services/api';
import {
  eligibilityMatchRate,
  flattenEligibilityRows,
  screeningHighlights,
  statusLabel,
  statusTone,
} from '../utils/eligibility';
import { asNumber, formatList, formatSalary, initials } from '../utils/formatters';
import './recruiterPages.css';

export default function CandidateDetailPage() {
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const [application, setApplication] = useState(null);
  const [result, setResult] = useState(null);
  const [resultMissing, setResultMissing] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evalOpen, setEvalOpen] = useState(false);
  const [transcriptQuery, setTranscriptQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const detail = await api.getApplication(applicationId);
        if (cancelled) return;
        setApplication(detail);
        try {
          const interview = await api.getInterviewResult(applicationId);
          if (!cancelled) {
            setResult(interview);
            setResultMissing(false);
          }
        } catch {
          if (!cancelled) {
            setResult(null);
            setResultMissing(true);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [applicationId]);

  if (loading) return <LoadingSpinner label="Loading candidate" />;
  if (error) return <ErrorState message={error.message} onRetry={() => navigate(0)} />;
  if (!application) return <EmptyState title="Application not found" />;

  const profile = application.candidate_profile || {};
  const rows = flattenEligibilityRows(application.eligibility_result);
  const matchRate = eligibilityMatchRate(application.eligibility_result);
  const highlights = screeningHighlights(application.eligibility_result);
  const skills = Array.isArray(result?.final_report?.skill_scores) ? result.final_report.skill_scores : [];
  const turns = (result?.qa_transcript?.turns || []).filter((turn) => {
    if (!transcriptQuery.trim()) return true;
    return `${turn.question || ''} ${turn.answer || ''}`.toLowerCase().includes(transcriptQuery.toLowerCase());
  });

  return (
    <div className="page">
      <div className="crumb">
        <Link to="/pipeline">Candidate Pipeline</Link>
        <span>/</span>
        <span>{application.job_title}</span>
      </div>

      <header className="detail-hero">
        <span className="avatar xl">{initials(application.candidate_full_name)}</span>
        <div>
          <h1 className="page-title">{application.candidate_full_name}</h1>
          <p className="page-subtitle">
            {application.job_title}
            {application.candidate_email ? ` · ${application.candidate_email}` : ''}
            {application.candidate_phone ? ` · ${application.candidate_phone}` : ''}
          </p>
          <div className="hero-chips">
            {matchRate != null ? (
              <Badge variant={application.overall_eligible ? 'pass' : 'fail'}>{matchRate}% requirements met</Badge>
            ) : (
              <Badge variant={application.overall_eligible ? 'pass' : 'fail'}>
                {application.overall_eligible ? 'Eligible' : 'Not eligible'}
              </Badge>
            )}
            <Badge variant={result ? 'pass' : 'neutral'}>{result ? 'Interview complete' : 'No interview result'}</Badge>
            <Badge variant={application.email_sent_at ? 'info' : 'neutral'}>
              {application.email_sent_at ? 'Invitation sent' : 'Invitation not marked sent'}
            </Badge>
            {application.hiring_decision === 'rejected' ? (
              <Badge variant="fail">Rejected</Badge>
            ) : null}
          </div>
        </div>
        <div className="hero-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEvalOpen(true)}>Evaluation</button>
          {result ? (
            <Link className="btn btn-secondary btn-sm" to={`/pipeline/${application.id}/assessment`}>Assessment report</Link>
          ) : null}
        </div>
      </header>

      <div className="detail-layout">
        <div className="detail-main">
          <Card title="AI Screening Results">
            {rows.length ? (
              <table className="data-table compact">
                <thead>
                  <tr>
                    <th>Requirement</th>
                    <th>Status</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.name}-${row.kind}`}>
                      <td>{row.name}</td>
                      <td><Badge variant={statusTone(row.status)}>{statusLabel(row.status)}</Badge></td>
                      <td className="muted">{row.details || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState
                title="No structured eligibility rows"
                description="This application is stored, but eligibility_result does not contain requirement-level matches."
              />
            )}
          </Card>

          <Card
            title="Interview transcript"
            action={
              <input
                className="inline-search"
                value={transcriptQuery}
                onChange={(event) => setTranscriptQuery(event.target.value)}
                placeholder="Search transcript"
              />
            }
          >
            {resultMissing ? (
              <EmptyState
                title="Report unavailable"
                description="No InterviewResult has been persisted for this application yet."
              />
            ) : null}
            {!resultMissing && !turns.length ? (
              <EmptyState title="No transcript turns" description="The interview result does not include QA transcript turns." />
            ) : null}
            {turns.map((turn, index) => (
              <article key={`${index}-${turn.question}`} className="transcript-turn spaced">
                <p className="q">AI Interviewer: {turn.question}</p>
                <p className="a">{application.candidate_full_name}: {turn.answer}</p>
              </article>
            ))}
            <p className="muted tiny">Interview recordings are not stored by the backend, so playback is unavailable.</p>
          </Card>
        </div>

        <aside className="detail-side">
          <Card title="AI Screening Summary">
            <Badge variant={application.overall_eligible ? 'pass' : 'fail'}>
              {application.overall_eligible ? 'Eligible' : 'Not eligible'}
              {matchRate != null ? ` · ${matchRate}% requirements met` : ''}
            </Badge>
            <p className="muted" style={{ marginTop: 10 }}>
              Salary expectation {formatSalary(application.salary_expectation)}. Availability: {application.joining_availability}.
            </p>
            {highlights.strengths.length ? (
              <div className="summary-block">
                <div className="eyebrow">Experience breakdown</div>
                <ul>{highlights.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
            {highlights.concerns.length ? (
              <div className="summary-block concern">
                <div className="eyebrow">Potential concern</div>
                <ul>{highlights.concerns.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
          </Card>

          <Card title="Skill verification depth">
            {skills.length ? (
              skills.map((skill) => (
                <ProgressBar
                  key={skill.skill_name}
                  label={skill.skill_name}
                  value={asNumber(skill.proficiency_score)}
                  tone={asNumber(skill.proficiency_score) >= 70 ? 'green' : 'lavender'}
                />
              ))
            ) : (
              <p className="muted">Skill scores appear after a persisted interview assessment.</p>
            )}
            {profile.skills?.length ? (
              <p className="muted tiny">CV skills: {formatList(profile.skills)}</p>
            ) : null}
          </Card>

          <Card title="Soft skill indicators">
            {result ? (
              <div className="soft-grid">
                <div>
                  <strong>{asNumber(result.communication_performance) == null ? '—' : Math.round(asNumber(result.communication_performance))}</strong>
                  <span>Communication</span>
                </div>
                <div>
                  <strong>{asNumber(result.problem_solving_performance) == null ? '—' : Math.round(asNumber(result.problem_solving_performance))}</strong>
                  <span>Problem solving</span>
                </div>
              </div>
            ) : (
              <EmptyState title="Not available" description="Soft-skill scores come from InterviewResult performance fields." />
            )}
          </Card>
        </aside>
      </div>

      <RecruiterDecisionBar
        application={application}
        onUpdated={(updated) => setApplication(updated)}
      />
      <EvaluationModal
        application={application}
        open={evalOpen}
        onClose={() => setEvalOpen(false)}
      />
    </div>
  );
}
