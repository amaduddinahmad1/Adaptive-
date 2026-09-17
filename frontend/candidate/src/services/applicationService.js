const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const APPLY_TIMEOUT_MS = 180000;

function errorMessage(payload, status) {
  if (!payload) return `Request failed (${status})`;
  if (typeof payload.detail === 'string') return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.msg || item?.detail || JSON.stringify(item))
      .join('; ');
  }
  return payload.message || `Request failed (${status})`;
}

async function request(path, { timeout = 8000, ...options } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
    });
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error('The application service did not respond. Please try again in a moment.');
    }
    throw new Error('Unable to reach the application service.');
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    throw new Error(errorMessage(payload, response.status));
  }
  return payload;
}

export async function listOpenJobs() {
  return request('/api/v1/jobs');
}

export async function resolveInterviewInvitation(token) {
  return request('/api/v1/interview-invitations/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
}

export async function submitApplication({
  jobId,
  fullName,
  email,
  phone,
  joiningAvailability,
  salaryExpectation,
  cvFile,
}) {
  const body = new FormData();
  body.append('full_name', fullName);
  body.append('email', email);
  if (phone) body.append('phone', phone);
  body.append('joining_availability', joiningAvailability);
  body.append('salary_expectation', String(salaryExpectation));
  body.append('cv', cvFile);

  return request(`/api/v1/jobs/${jobId}/apply`, {
    method: 'POST',
    body,
    timeout: APPLY_TIMEOUT_MS,
  });
}
