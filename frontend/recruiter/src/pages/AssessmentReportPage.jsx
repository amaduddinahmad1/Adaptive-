import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ErrorState from '../components/common/Alert';
import Badge from '../components/common/Badge';
import Card from '../components/common/Card';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ProgressBar from '../components/common/ProgressBar';
import RecruiterDecisionBar from '../components/candidate/RecruiterDecisionBar';
import { api } from '../services/api';
import { flattenEligibilityRows, recommendationTone, statusLabel } from '../utils/eligibility';
import { asNumber, formatPercent, initials } from '../utils/formatters';
import './recruiterPages.css';

export default function AssessmentReportPage() {
  const { applicationId } = useParams();
  const [application, setApplication] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [missing, setMissing] = useState(false);
  const [loading, setLoading] = useState(true);

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
            setMissing(false);
          }
        } catch {
          if (!cancelled) {
            setResult(null);
            setMissing(true);
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

  if (loading) return <LoadingSpinner label="Loading assessment" />;
  if (error) return <ErrorState message={error.message} />;
  if (missing || !result) {
    return (
      <div className="page">
        <div className="crumb">
          <Link to="/pipeline">Pipeline</Link>
          <span>/</span>
          <Link to={`/pipeline/${applicationId}`}>{application?.candidate_full_name || 'Candidate'}</Link>
          <span>/</span>
          <span>Candidate Assessment</span>
        </div>
        <EmptyState
          title="Assessment report unavailable"
          description="This interview is incomplete or no InterviewResult has been persisted yet. Scores are never generated in the UI."
        />
      </div>
    );
  }

  const report = result.final_report || {};
  const skills = Array.isArray(report.skill_scores) ? report.skill_scores : [];
  const gaps = Array.isArray(result.gap_analysis?.entries) ? result.gap_analysis.entries : [];
  const eligibilityRows = flattenEligibilityRows(application?.eligibility_result);
  const demonstrated = gaps.filter((entry) => {
    const alignment = String(entry.alignment || '').toLowerCase();
    return alignment === 'strong' || alignment === 'moderate';
  });
  const missingEvidence = gaps.filter((entry) => !demonstrated.includes(entry));

  return (
    <div className="page assessment-page">
      <div className="crumb">
        <Link to="/pipeline">Pipeline</Link>
        <span>/</span>
        <span>{result.job_title}</span>
        <span>/</span>
        <span>Candidate Assessment</span>
      </div>

      <header className="assess-hero">
        <span className="avatar xl">{initials(result.candidate_full_name)}</span>
        <div>
          <h1 className="page-title">{result.candidate_full_name}</h1>
          <p className="page-subtitle">{result.candidate_email} · {result.job_title}</p>
          <Badge variant={recommendationTone(result.recommendation)}>{result.recommendation}</Badge>
          {application?.hiring_decision === 'rejected' ? (
            <Badge variant="fail">Rejected</Badge>
          ) : null}
        </div>
        <div className="metric-grid mini">
          <StatsMini label="Interview eligibility" value={result.interview_eligibility_result} />
          <StatsMini label="Problem solving" value={formatPercent(result.problem_solving_performance)} />
          <StatsMini label="Communication" value={formatPercent(result.communication_performance)} />
          <StatsMini label="CV consistency" value={consistencyLabel(report.cv_interview_consistency)} />
        </div>
      </header>

      <div className="split-2">
        <Card title="Experience & eligibility">
          {eligibilityRows.length ? (
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>JD req</th>
                  <th>CV claim</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {eligibilityRows.map((row) => (
                  <tr key={`${row.name}-${row.kind}`}>
                    <td>{row.name}</td>
                    <td>{row.yearsRequired != null ? `≥ ${row.yearsRequired}` : '—'}</td>
                    <td>{row.yearsFound != null ? row.yearsFound : '—'}</td>
                    <td>{statusLabel(row.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState title="No eligibility matrix" description="Application eligibility rows are not available." />
          )}
        </Card>

        <div className="stack">
          <Card title="Skill verification depth">
            {skills.length ? skills.map((skill) => (
              <ProgressBar
                key={skill.skill_name}
                label={skill.skill_name}
                value={asNumber(skill.proficiency_score)}
                tone={asNumber(skill.proficiency_score) >= 75 ? 'green' : asNumber(skill.proficiency_score) >= 60 ? 'lavender' : 'amber'}
              />
            )) : <p className="muted">No skill scores in the final report.</p>}
          </Card>
          <Card title="CV claim vs interview evidence gap">
            {gaps.length ? (
              <div className="gap-cols">
                <div>
                  <div className="eyebrow">Demonstrated / aligned</div>
                  <ul>{(demonstrated.length ? demonstrated : gaps.slice(0, 0)).map((entry) => <li key={entry.skill}>{entry.skill}: {entry.alignment}</li>)}</ul>
                  {!demonstrated.length ? <p className="muted">No aligned gap entries.</p> : null}
                </div>
                <div>
                  <div className="eyebrow">Missing areas</div>
                  <ul>{missingEvidence.map((entry) => <li key={entry.skill}>{entry.skill}: {entry.cv_claim || entry.alignment}</li>)}</ul>
                </div>
              </div>
            ) : (
              <p className="muted">No gap analysis entries were persisted.</p>
            )}
            {report.recommendation_reason ? <p className="muted">{report.recommendation_reason}</p> : null}
          </Card>
        </div>
      </div>

      <Card title="Interview plan & Q&A">
        {result.interview_plan ? (
          <p className="muted">
            Skill areas: {(result.interview_plan.skill_areas || []).join(', ') || '—'}. Estimated time: {result.interview_plan.estimated_time ?? '—'} min.
          </p>
        ) : <p className="muted">No interview plan stored.</p>}
        {(result.qa_transcript?.turns || []).map((turn, index) => (
          <article key={index} className="transcript-turn spaced">
            <p className="q">{turn.question}</p>
            <p className="a">{turn.answer}</p>
            {turn.evaluation?.weighted_total != null ? (
              <p className="muted tiny">Answer score: {Math.round(turn.evaluation.weighted_total)}</p>
            ) : null}
          </article>
        ))}
      </Card>

      <RecruiterDecisionBar
        application={application}
        onUpdated={(updated) => setApplication(updated)}
      />
    </div>
  );
}

function StatsMini({ label, value }) {
  return (
    <div className="metric-card mini">
      <span className="eyebrow">{label}</span>
      <div className="metric-value small">{value || '—'}</div>
    </div>
  );
}

function consistencyLabel(value) {
  if (!value || typeof value !== 'object') return '—';
  const matched = Number(
    value.matched
    ?? value.matched_claims
    ?? (Number(value.Strong || 0) + Number(value.Moderate || 0)),
  );
  const unmatched = Number(value.unmatched ?? value.unmatched_claims ?? value.Weak ?? 0);
  if (!matched && !unmatched) return '—';
  const total = matched + unmatched;
  return formatPercent((matched / total) * 100);
}
