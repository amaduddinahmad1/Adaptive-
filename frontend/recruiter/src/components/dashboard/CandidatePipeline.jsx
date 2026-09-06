import './CandidatePipeline.css';
import Card from '../common/Card';
export default function CandidatePipeline() {
  const stages = [
    { label: 'Applied', count: 145, color: '#3b82f6' },
    { label: 'Screening', count: 86, color: '#8b5cf6' },
    { label: 'Interview', count: 42, color: '#f59e0b' },
    { label: 'Offer', count: 12, color: '#10b981' }
  ];
  return (
    <Card className="pipeline-card">
      <h3 className="card-title">Candidate Pipeline</h3>
      <div className="pipeline-stages">
        {stages.map((stage, idx) => (
          <div key={idx} className="pipeline-stage">
            <div className="stage-header">
              <span className="stage-label">{stage.label}</span>
              <span className="stage-count">{stage.count}</span>
            </div>
            <div className="stage-bar">
              <div className="stage-progress" style={{ width: '100%', backgroundColor: stage.color }}></div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
