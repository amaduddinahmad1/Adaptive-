import EmptyState from '../components/common/EmptyState';
import PageHeader from '../components/layout/PageHeader';

export default function CandidatesPage() {
  return (
    <div>
      <PageHeader title="Candidate Database" />
      <EmptyState title="Candidates Coming Soon" description="View and filter your talent pool." icon="👥" />
    </div>
  );
}
