const PASS_STATUSES = new Set(['met', 'met_by_inference']);
const FAIL_STATUSES = new Set(['not_met_mandatory']);
const REVIEW_STATUSES = new Set(['manual_review_required']);

export function statusTone(status) {
  const key = String(status || '').toLowerCase();
  if (PASS_STATUSES.has(key)) return 'pass';
  if (FAIL_STATUSES.has(key)) return 'fail';
  if (REVIEW_STATUSES.has(key)) return 'review';
  if (key === 'not_found_preferred') return 'miss';
  return 'neutral';
}

export function statusLabel(status) {
  const tone = statusTone(status);
  if (tone === 'pass') return 'Pass';
  if (tone === 'fail') return 'Fail';
  if (tone === 'review') return 'Review';
  if (tone === 'miss') return 'Preferred';
  return status ? String(status).replace(/_/g, ' ') : '—';
}

function requirementName(entry) {
  if (!entry || typeof entry !== 'object') return '';
  if (entry.match?.description) return entry.match.description;
  if (entry.match?.target) return entry.match.target;
  if (entry.requirement?.requirement) return entry.requirement.requirement;
  if (typeof entry.requirement === 'string') return entry.requirement;
  return '';
}

export function flattenEligibilityRows(eligibilityResult) {
  if (!eligibilityResult || typeof eligibilityResult !== 'object') return [];
  const rows = [];

  (eligibilityResult.experience_results || []).forEach((entry) => {
    rows.push({
      name: requirementName(entry) || 'Experience',
      status: entry.status,
      details: entry.match
        ? `${entry.match.candidate_years ?? '—'} yrs vs ${entry.match.required_years ?? '—'} required`
        : entry.reason || '',
      yearsRequired: entry.match?.required_years,
      yearsFound: entry.match?.candidate_years,
      kind: 'experience',
    });
  });

  (eligibilityResult.requirement_results || []).forEach((entry) => {
    rows.push({
      name: requirementName(entry) || 'Requirement',
      status: entry.status,
      details: entry.reason || '',
      kind: 'requirement',
    });
  });

  if (eligibilityResult.joining_availability_result) {
    const item = eligibilityResult.joining_availability_result;
    rows.push({
      name: 'Joining Availability',
      status: item.status,
      details: item.candidate_joining_availability || '',
      kind: 'joining',
    });
  }

  if (eligibilityResult.salary_result) {
    const item = eligibilityResult.salary_result;
    rows.push({
      name: 'Salary Expectation',
      status: item.status,
      details: item.candidate_salary_expectation != null
        ? `Expectation ${item.candidate_salary_expectation}`
        : '',
      kind: 'salary',
    });
  }

  return rows;
}

export function eligibilityMatchRate(eligibilityResult) {
  const rows = flattenEligibilityRows(eligibilityResult).filter((row) => row.status);
  if (!rows.length) return null;
  const scored = rows.filter((row) => statusTone(row.status) !== 'miss');
  if (!scored.length) return null;
  const passed = scored.filter((row) => statusTone(row.status) === 'pass').length;
  return Math.round((passed / scored.length) * 100);
}

export function screeningHighlights(eligibilityResult) {
  const rows = flattenEligibilityRows(eligibilityResult);
  const strengths = rows
    .filter((row) => statusTone(row.status) === 'pass')
    .slice(0, 3)
    .map((row) => row.details || `${row.name} met.`);
  const concerns = rows
    .filter((row) => statusTone(row.status) === 'fail' || statusTone(row.status) === 'review')
    .slice(0, 3)
    .map((row) => row.details || `${row.name} needs review.`);
  return { strengths, concerns };
}

export function isRejected(application) {
  return String(application?.hiring_decision || '').toLowerCase() === 'rejected';
}

export function interviewStatus(application) {
  if (!application) return { label: 'Not started', tone: 'neutral' };
  if (isRejected(application)) return { label: 'Rejected', tone: 'fail' };
  if (application.has_interview_result) return { label: 'Completed', tone: 'pass' };
  if (application.token_used) return { label: 'In progress', tone: 'info' };
  if (application.email_sent_at) return { label: 'Invited', tone: 'info' };
  if (application.overall_eligible) return { label: 'Eligible', tone: 'pass' };
  return { label: 'Not eligible', tone: 'fail' };
}

export function recommendationTone(value) {
  const key = String(value || '').toLowerCase();
  if (key.includes('hire') && !key.includes('further')) return 'pass';
  if (key.includes('decline') || key.includes('reject')) return 'fail';
  if (key.includes('further') || key.includes('eval')) return 'review';
  return 'neutral';
}
