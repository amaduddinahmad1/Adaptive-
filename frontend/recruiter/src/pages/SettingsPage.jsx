import EmptyState from '../components/common/EmptyState';
import PageHeader from '../components/layout/PageHeader';

export default function SettingsPage() {
  return (
    <div>
      <PageHeader title="Settings" />
      <EmptyState title="Settings Coming Soon" description="Configure your recruiting workspace." icon="⚙️" />
    </div>
  );
}
