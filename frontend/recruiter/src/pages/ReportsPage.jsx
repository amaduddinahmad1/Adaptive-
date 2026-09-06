import EmptyState from '../components/common/EmptyState';
import PageHeader from '../components/layout/PageHeader';

export default function ReportsPage() {
  return (
    <div>
      <PageHeader title="Analytics & Reports" />
      <EmptyState title="Reports Coming Soon" description="Deep dive into your hiring metrics." icon="📈" />
    </div>
  );
}
