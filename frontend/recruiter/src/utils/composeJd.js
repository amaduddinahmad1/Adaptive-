/**
 * Compose recruiter job-form fields into JD text for the existing JD parser.
 *
 * Preferred skills/technologies stay in their own sections and are stripped
 * from the required sections when the same name is entered in both, so they
 * are not classified as mandatory. Empty fields are omitted; nothing is
 * invented (no default FastAPI/PostgreSQL/etc.).
 */

function trimText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function splitRequirementItems(value) {
  const text = trimText(value);
  if (!text) return [];

  return text
    .split(/\r?\n/)
    .flatMap((line) => line.split(','))
    .flatMap((part) => part.split(/\s+-\s+/))
    .map((item) => item.replace(/^[-•*]\s*/, '').trim())
    .filter(Boolean);
}

function uniqueByLower(items) {
  const seen = new Set();
  const unique = [];
  items.forEach((item) => {
    const key = item.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    unique.push(item);
  });
  return unique;
}

export function excludePreferredItems(requiredItems, preferredItems) {
  const preferred = new Set(
    preferredItems.map((item) => item.trim().toLowerCase()).filter(Boolean)
  );
  return requiredItems.filter((item) => !preferred.has(item.trim().toLowerCase()));
}

function section(label, items) {
  if (!items.length) return '';
  return `${label}: ${items.join(', ')}`;
}

export function composeJd(form = {}) {
  const preferredSkills = uniqueByLower(splitRequirementItems(form.preferredSkills));
  const requiredSkills = uniqueByLower(
    excludePreferredItems(splitRequirementItems(form.requiredSkills), preferredSkills)
  );
  const preferredTech = uniqueByLower(splitRequirementItems(form.preferredTech));
  const requiredTech = uniqueByLower(
    excludePreferredItems(splitRequirementItems(form.requiredTech), preferredTech)
  );

  const jobTitle = trimText(form.jobTitle);
  const department = trimText(form.department);
  const location = trimText(form.location);
  const salaryMin = trimText(form.salaryMin);
  const salaryMax = trimText(form.salaryMax);
  const screeningRules = trimText(form.screeningRules);
  const jdText = trimText(form.jdText);

  const lines = [
    jobTitle && `Job title: ${jobTitle}`,
    department && `Department: ${department}`,
    location && `Location: ${location}`,
    (salaryMin || salaryMax) && `Salary range: ${salaryMin} - ${salaryMax}`,
    section('Required skills', requiredSkills),
    section('Preferred skills', preferredSkills),
    section('Required technologies', requiredTech),
    section('Preferred technologies', preferredTech),
    screeningRules && `Mandatory screening requirements:\n${screeningRules}`,
    jdText,
  ].filter(Boolean);

  return lines.join('\n\n');
}
