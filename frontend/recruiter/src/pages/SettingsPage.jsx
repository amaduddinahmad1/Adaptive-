import Card from '../components/common/Card';
import { useAuth } from '../context/AuthContext';
import './recruiterPages.css';

export default function SettingsPage() {
  const { recruiter } = useAuth();
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Workspace preferences. Authentication is enforced by the backend JWT recruiter session.</p>
        </div>
      </div>
      <div className="split-2">
        <Card title="Workspace">
          <dl className="kv">
            <div><dt>Product</dt><dd>InterviewAI</dd></div>
            <div><dt>Tier</dt><dd>Enterprise Recruiter</dd></div>
            <div><dt>Signed in as</dt><dd>{recruiter?.full_name || 'Recruiter'}</dd></div>
            <div><dt>Email</dt><dd>{recruiter?.email || '—'}</dd></div>
            <div><dt>Invitations</dt><dd>Eligible candidates already receive a 48-hour interview link from the existing backend flow</dd></div>
          </dl>
        </Card>
        <Card title="AI behavior">
          <p className="muted">
            Eligibility, interview intelligence, assessment, LiveKit, STT, TTS, and anti-cheat stay on the backend.
            Recruiter settings in this phase are display-only.
          </p>
        </Card>
      </div>
    </div>
  );
}
