import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ErrorState from '../components/common/Alert';
import Badge from '../components/common/Badge';
import Card from '../components/common/Card';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useAsync } from '../hooks/useAsync';
import { api } from '../services/api';
import { interviewStatus } from '../utils/eligibility';
import { initials } from '../utils/formatters';
import './recruiterPages.css';

export default function LiveSessionsPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [sessions, applications] = await Promise.all([
      api.listVoiceSessions(),
      api.listApplications(true),
    ]);
    return { sessions, applications };
  }, []);

  if (loading) return <LoadingSpinner label="Loading sessions" />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;

  const sessions = data?.sessions || [];
  const applications = data?.applications || [];

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Live AI Sessions</h1>
          <p className="page-subtitle">In-memory voice sessions plus eligible applications. This view does not control LiveKit, STT, or TTS.</p>
        </div>
      </div>
      <div className="split-2">
        <Card title="Active voice sessions">
          {sessions.length ? (
            <div className="stack-list">
              {sessions.map((session) => (
                <Link key={session.session_id} className="stack-row" to={`/sessions/${session.session_id}`}>
                  <span>
                    <strong>Application #{session.application_id}</strong>
                    <small>{session.interview_status} · {session.connection_status}</small>
                  </span>
                  <Badge variant="info">{session.interview_status}</Badge>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No live sessions in memory"
              description="Sessions exist only while the backend voice service is running. Start an interview from an eligible candidate invitation to populate this list."
            />
          )}
        </Card>
        <Card title="Eligible applications">
          {applications.length ? applications.slice(0, 8).map((row) => {
            const status = interviewStatus(row);
            return (
              <Link key={row.id} className="stack-row" to={`/pipeline/${row.id}`}>
                <span className="avatar">{initials(row.candidate_full_name)}</span>
                <span>
                  <strong>{row.candidate_full_name}</strong>
                  <small>{row.job_title}</small>
                </span>
                <Badge variant={status.tone}>{status.label}</Badge>
              </Link>
            );
          }) : <EmptyState title="No eligible applications" />}
        </Card>
      </div>
    </div>
  );
}

export function LiveSessionDetailPage() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [application, setApplication] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const voice = await api.getVoiceSession(sessionId);
        if (cancelled) return;
        setSession(voice);
        if (voice.application_id) {
          const detail = await api.getApplication(voice.application_id);
          if (cancelled) return;
          setApplication(detail);
          try {
            const interview = await api.getInterviewResult(voice.application_id);
            if (!cancelled) setResult(interview);
          } catch {
            if (!cancelled) setResult(null);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const timer = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sessionId]);

  if (loading && !session) return <LoadingSpinner label="Loading live session" />;
  if (error) return <ErrorState message={error.message} />;
  if (!session) return <EmptyState title="Session not found" description="Voice sessions are in-memory and disappear when the backend restarts." />;

  const tech = application?.job_profile_snapshot?.required_technologies || application?.candidate_profile?.technologies || [];
  const turns = result?.qa_transcript?.turns || [];

  return (
    <div className="page live-page">
      <div className="crumb">
        <Link to="/sessions">Live AI Sessions</Link>
        <span>/</span>
        <span>{session.session_id.slice(0, 8)}</span>
      </div>
      <div className="live-grid">
        <aside className="live-left">
          <Card>
            <div className="person-cell">
              <span className="avatar xl">{initials(application?.candidate_full_name)}</span>
              <span>
                <strong>{application?.candidate_full_name || `Candidate ${session.candidate_id}`}</strong>
                <small>{application?.job_title || `Job ${session.job_id}`}</small>
              </span>
            </div>
            <div style={{ marginTop: 12 }}>
              <Badge variant={application?.overall_eligible ? 'pass' : 'neutral'}>
                {application?.overall_eligible ? 'Eligible' : 'Eligibility unknown'}
              </Badge>
            </div>
          </Card>
          <Card title="Technical requirements">
            {tech.length ? (
              <div className="chip-row">
                {tech.slice(0, 8).map((item) => (
                  <span key={item} className="chip">{item}</span>
                ))}
              </div>
            ) : (
              <p className="muted">No required technologies on the job snapshot.</p>
            )}
            <p className="muted tiny">Proficiency bars appear on the assessment report when an InterviewResult exists.</p>
          </Card>
        </aside>

        <section className="live-stage panel">
          <div className="live-stage-top">
            <Badge variant="info">{session.interview_status}</Badge>
            <Badge variant="neutral">{session.connection_status}</Badge>
          </div>
          <div className="orb" aria-hidden="true" />
          <div className="current-q">
            <div className="eyebrow">Current AI question</div>
            <p>{session.current_question || 'No current question is published on this session.'}</p>
          </div>
          <div className="live-controls">
            <button type="button" className="btn btn-ghost btn-sm" disabled>Mute</button>
            <button type="button" className="btn btn-ghost btn-sm" disabled>Pause interview</button>
            <button type="button" className="btn btn-danger btn-sm" disabled>Intervene</button>
          </div>
          <p className="muted tiny">Transport controls stay disabled so this UI cannot change LiveKit, STT, TTS, or anti-cheat behavior.</p>
        </section>

        <aside className="live-right">
          <Card title="Live transcript">
            {turns.length ? turns.map((turn, index) => (
              <article key={index} className="transcript-turn spaced">
                <p className="q">{turn.question}</p>
                <p className="a">{turn.answer}</p>
              </article>
            )) : (
              <EmptyState
                title="Live transcript not streamed"
                description="The voice API does not expose a live transcript feed. Turns appear here after an InterviewResult is persisted."
              />
            )}
          </Card>
          <Card title="System telemetry">
            <EmptyState title="Not provided" description="Latency, processing load, and model confidence are not backend fields." />
          </Card>
        </aside>
      </div>
    </div>
  );
}
