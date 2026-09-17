export default function SkillIndicator({ label, value }) {
  return (
    <div className="skill-bar">
      <div className="skill-bar-label">
        <span>{label}</span>
        <strong>{value ?? '—'}</strong>
      </div>
    </div>
  );
}
