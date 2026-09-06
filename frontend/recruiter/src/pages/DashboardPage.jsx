import './DashboardPage.css';
import PageHeader from '../components/layout/PageHeader';
import StatsCard from '../components/dashboard/StatsCard';
import CandidatePipeline from '../components/dashboard/CandidatePipeline';
import RecentActivity from '../components/dashboard/RecentActivity';
import Button from '../components/common/Button';

export default function DashboardPage() {
  return (
    <div className="dashboard-page">
      <PageHeader 
        title="Dashboard Overview" 
        description="Welcome back! Here's what's happening with your hiring pipeline."
        action={<Button variant="primary">+ New Job Post</Button>}
      />
      <div className="stats-grid">
        <StatsCard title="Total Jobs" value="12" trend={5} icon="💼" />
        <StatsCard title="Active Candidates" value="145" trend={12} icon="👥" />
        <StatsCard title="Interviews Today" value="8" trend={-2} icon="📅" />
        <StatsCard title="Avg. AI Score" value="78%" trend={4} icon="🤖" />
      </div>
      <div className="dashboard-columns">
        <CandidatePipeline />
        <RecentActivity />
      </div>
    </div>
  );
}
