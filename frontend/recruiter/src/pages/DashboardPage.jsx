import { Link } from 'react-router-dom';
import ErrorState from '../components/common/Alert';
import Badge from '../components/common/Badge';
import Card from '../components/common/Card';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatsCard from '../components/dashboard/StatsCard';
import { Icon } from '../components/common/Icons';
import { useAsync } from '../hooks/useAsync';
import { api } from '../services/api';
import { interviewStatus } from '../utils/eligibility';
import { initials, relativeTime } from '../utils/formatters';
import './recruiterPages.css';

export default function DashboardPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [applications, jobs, candidates] = await Promise.all([
      api.listApplications(),
      api.listJobs(),
      api.listCandidates(),
    ]);
    return { applications, jobs, candidates };
  }, []);

  if (loading) return <LoadingSpinner label="Loading dashboard" />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;

  const applications = data?.applications || [];
  const jobs = data?.jobs || [];
  const candidates = data?.candidates || [];
  const eligible = applications.filter((row) => row.overall_eligible).length;
  const completed = applications.filter((row) => row.has_interview_result).length;
  const recent = applications.slice(0, 6);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">Recruiter workspace</div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Live counts from persisted candidates, applications, and interview results.</p>
        </div>
        <Link to="/jobs/new" className="btn btn-primary btn-md">New Job Posting</Link>
      </div>

      <div className="metric-grid">
        <StatsCard title="Total applicants" value={applications.length} hint={`${candidates.length} unique candidates`} icon={<Icon name="users" size={16} />} />
        <StatsCard title="Eligible" value={eligible} hint="Passed application eligibility" icon={<Icon name="check" size={16} />} />
        <StatsCard title="Completed interviews" value={completed} hint="Applications with InterviewResult" icon={<Icon name="waveform" size={16} />} />
        <StatsCard title="Job postings" value={jobs.length} hint="Parsed JD profiles on file" icon={<Icon name="briefcase" size={16} />} />
      </div>

      <div className="split-2">
        <Card title="Recent applications" action={<Link to="/pipeline" className="text-link">Open pipeline</Link>}>
          {recent.length ? (
            <div className="stack-list">
              {recent.map((row) => {
                const status = interviewStatus(row);
                return (
                  <Link key={row.id} to={`/pipeline/${row.id}`} className="stack-row">
                    <span className="avatar">{initials(row.candidate_full_name)}</span>
                    <span>
                      <strong>{row.candidate_full_name}</strong>
                      <small>{row.job_title} · {relativeTime(row.created_at)}</small>
                    </span>
                    <Badge variant={status.tone}>{status.label}</Badge>
                  </Link>
                );
              })}
            </div>
          ) : (
            <EmptyState title="No applications yet" description="When candidates submit applications, they will appear here." />
          )}
        </Card>
        <Card title="Active postings" action={<Link to="/jobs" className="text-link">Manage jobs</Link>}>
          {jobs.length ? (
            <div className="stack-list">
              {jobs.slice(0, 6).map((job) => (
                <Link key={job.id} to={`/jobs/${job.id}`} className="stack-row">
                  <span>
                    <strong>{job.job_title}</strong>
                    <small>{job.application_count} applicants</small>
                  </span>
                  <Badge variant="info">Recruiting</Badge>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="No job postings" description="Create a posting to start screening candidates." />
          )}
        </Card>
      </div>
    </div>
  );
}
