import EmptyState from '../components/common/EmptyState';
import PageHeader from '../components/layout/PageHeader';

export default function JobsPage() {
  return (
    <div>
      <PageHeader title="Jobs Management" />
      <EmptyState title="Jobs Coming Soon" description="Create and manage your job postings here." icon="💼" />
    </div>
  );
}
