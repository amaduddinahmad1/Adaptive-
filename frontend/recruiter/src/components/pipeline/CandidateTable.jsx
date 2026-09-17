import { Link } from 'react-router-dom';
import Badge from '../common/Badge';
import Button from '../common/Button';
import EmptyState from '../common/EmptyState';
import { interviewStatus } from '../../utils/eligibility';
import { initials } from '../../utils/formatters';
import './CandidateTable.css';

export default function CandidateTable({ rows, onOpenEvaluation }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No applications match these filters"
        description="Try another search, role, or eligibility filter. This table only shows real backend applications."
      />
    );
  }

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>Candidate</th>
            <th>Applied Role</th>
            <th>Eligibility</th>
            <th>Availability</th>
            <th>Interview</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const status = interviewStatus(row);
            return (
              <tr key={row.id}>
                <td>
                  <Link className="person-cell" to={`/pipeline/${row.id}`}>
                    <span className="avatar">{initials(row.candidate_full_name)}</span>
                    <span>
                      <strong>{row.candidate_full_name}</strong>
                      <small>{row.candidate_email}</small>
                    </span>
                  </Link>
                </td>
                <td>
                  <div className="role-cell">
                    <strong>{row.job_title}</strong>
                    <small>Application #{row.id}</small>
                  </div>
                </td>
                <td>
                  <Badge variant={row.overall_eligible ? 'pass' : 'fail'}>
                    {row.overall_eligible ? 'Eligible' : 'Not eligible'}
                  </Badge>
                </td>
                <td className="muted">{row.joining_availability || '—'}</td>
                <td>
                  <Badge variant={status.tone}>{status.label}</Badge>
                </td>
                <td className="row-actions">
                  <Button size="sm" variant="ghost" onClick={() => onOpenEvaluation(row)}>
                    Evaluation
                  </Button>
                  <Link className="text-link" to={`/pipeline/${row.id}`}>
                    Open
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
