import ErrorState from '../components/common/Alert';
import Card from '../components/common/Card';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatsCard from '../components/dashboard/StatsCard';
import { useAsync } from '../hooks/useAsync';
import { api } from '../services/api';
import { formatPercent } from '../utils/formatters';
import './recruiterPages.css';

export default function AnalyticsPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [applications, jobs] = await Promise.all([
      api.listApplications(),
      api.listJobs(),
    ]);
    return { applications, jobs };
  }, []);

  if (loading) return <LoadingSpinner label="Loading analytics" />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;

  const applications = data?.applications || [];
  const jobs = data?.jobs || [];
  const eligible = applications.filter((row) => row.overall_eligible).length;
  const completed = applications.filter((row) => row.has_interview_result).length;
  const passRatio = applications.length ? (eligible / applications.length) * 100 : null;
  const completionRate = eligible ? (completed / eligible) * 100 : null;
  const maxFunnel = Math.max(applications.length, eligible, completed, 1);

  const skillCounts = {};
  jobs.forEach((job) => {
    [...(job.required_skills || []), ...(job.required_technologies || [])].forEach((skill) => {
      const key = skill.trim();
      if (!key) return;
      skillCounts[key] = (skillCounts[key] || 0) + 1;
    });
  });
  const skills = Object.entries(skillCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const skillMax = Math.max(1, ...skills.map(([, count]) => count));

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Analytics Overview</h1>
          <p className="page-subtitle">Counts derived from dashboard applications and jobs. Unsupported PDF metrics stay empty.</p>
        </div>
        <span className="live-pill">Live data</span>
      </div>

      <div className="metric-grid">
        <StatsCard title="Avg. processing time" empty hint="Not returned by the backend" />
        <StatsCard
          title="Pass / fail ratio"
          value={passRatio == null ? '—' : formatPercent(passRatio)}
          hint={applications.length ? `${eligible} eligible of ${applications.length} applications` : 'No applications'}
        />
        <StatsCard
          title="Completion rate"
          value={completionRate == null ? '—' : formatPercent(completionRate)}
          hint={eligible ? `${completed} interview results / ${eligible} eligible` : 'No eligible applications'}
        />
        <StatsCard title="Efficiency gain" empty hint="Not returned by the backend" />
      </div>

      <div className="analytics-grid">
        <Card title="Recruitment funnel">
          {applications.length ? (
            <div className="funnel">
              <FunnelBar label="Applied" value={applications.length} max={maxFunnel} />
              <FunnelBar label="Eligible" value={eligible} max={maxFunnel} tone="green" />
              <FunnelBar label="Completed" value={completed} max={maxFunnel} tone="lavender" />
              <div className="funnel-col empty">
                <div className="funnel-bar" />
                <strong>—</strong>
                <span>Hired</span>
                <small>No hired field</small>
              </div>
            </div>
          ) : (
            <EmptyState title="No funnel data" description="Applications must exist before a funnel can be drawn." />
          )}
        </Card>
        <div className="stack">
          <Card title="Rejection distribution">
            <EmptyState
              title="Not supported"
              description="The backend does not persist rejection reasons or hiring outcomes."
            />
          </Card>
          <Card title="Skill density">
            {skills.length ? (
              <div className="heat">
                {skills.map(([skill, count]) => (
                  <div key={skill} className="heat-row">
                    <span>{skill}</span>
                    <div className="heat-cells">
                      {Array.from({ length: 4 }).map((_, index) => (
                        <i
                          key={index}
                          style={{ opacity: count / skillMax > index / 4 ? 0.35 + index * 0.2 : 0.12 }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No parsed skills on job summaries" />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function FunnelBar({ label, value, max, tone = 'white' }) {
  const height = Math.max(18, Math.round((value / max) * 180));
  return (
    <div className="funnel-col">
      <div className={`funnel-bar ${tone}`} style={{ height }} />
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
