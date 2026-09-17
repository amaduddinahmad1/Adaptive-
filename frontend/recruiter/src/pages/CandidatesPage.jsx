import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ErrorState from '../components/common/Alert';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatsCard from '../components/dashboard/StatsCard';
import EvaluationModal from '../components/candidate/EvaluationModal';
import CandidateTable from '../components/pipeline/CandidateTable';
import { Icon } from '../components/common/Icons';
import { useAsync } from '../hooks/useAsync';
import { api } from '../services/api';
import './recruiterPages.css';

export default function PipelinePage() {
  const [params, setParams] = useSearchParams();
  const [jobFilter, setJobFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const query = params.get('q') || '';

  const { data, error, loading, reload } = useAsync(() => api.listApplications(), []);

  const applications = useMemo(() => data || [], [data]);
  const jobs = useMemo(
    () => [...new Set(applications.map((row) => row.job_title).filter(Boolean))],
    [applications]
  );

  const filtered = applications.filter((row) => {
    const haystack = `${row.candidate_full_name} ${row.candidate_email} ${row.job_title}`.toLowerCase();
    if (query && !haystack.includes(query.toLowerCase())) return false;
    if (jobFilter !== 'all' && row.job_title !== jobFilter) return false;
    if (statusFilter === 'eligible' && !row.overall_eligible) return false;
    if (statusFilter === 'ineligible' && row.overall_eligible) return false;
    if (statusFilter === 'completed' && !row.has_interview_result) return false;
    if (statusFilter === 'pending' && row.has_interview_result) return false;
    if (statusFilter === 'rejected' && row.hiring_decision !== 'rejected') return false;
    return true;
  });

  const eligible = applications.filter((row) => row.overall_eligible).length;
  const completed = applications.filter((row) => row.has_interview_result).length;

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Candidate Pipeline</h1>
          <p className="page-subtitle">Manage and screen applicants with AI eligibility and interview status from the backend.</p>
        </div>
      </div>

      {loading ? <LoadingSpinner label="Loading applications" /> : null}
      {error ? <ErrorState message={error.message} onRetry={reload} /> : null}

      {!loading && !error ? (
        <>
          <div className="metric-grid">
            <StatsCard title="Total applicants" value={applications.length} icon={<Icon name="users" size={16} />} />
            <StatsCard title="Eligible" value={eligible} hint="Application eligibility gate" icon={<Icon name="check" size={16} />} />
            <StatsCard title="Completed interviews" value={completed} icon={<Icon name="waveform" size={16} />} />
            <StatsCard title="Shortlisted / hired" empty hint="Hire is not persisted. Rejection is stored on the application." />
          </div>

          <section className="panel table-panel">
            <div className="filters">
              <label className="search-field">
                <Icon name="search" size={15} />
                <input
                  value={query}
                  onChange={(event) => {
                    const next = new URLSearchParams(params);
                    if (event.target.value) next.set('q', event.target.value);
                    else next.delete('q');
                    setParams(next, { replace: true });
                  }}
                  placeholder="Search by candidate name, email, or role..."
                />
              </label>
              <select value={jobFilter} onChange={(event) => setJobFilter(event.target.value)}>
                <option value="all">All roles</option>
                {jobs.map((job) => (
                  <option key={job} value={job}>{job}</option>
                ))}
              </select>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="eligible">Eligible</option>
                <option value="ineligible">Not eligible</option>
                <option value="completed">Interview complete</option>
                <option value="pending">Interview pending</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <CandidateTable rows={filtered} onOpenEvaluation={setSelected} />
            <div className="table-foot">Showing {filtered.length} of {applications.length} applications</div>
          </section>
        </>
      ) : null}

      <EvaluationModal application={selected} open={Boolean(selected)} onClose={() => setSelected(null)} />
    </div>
  );
}
