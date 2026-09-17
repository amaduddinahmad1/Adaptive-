import { getAccessToken, notifyUnauthorized } from './authStorage';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const LLM_TIMEOUT_MS = 180000;

function errorMessage(payload, status) {
  if (payload && typeof payload.detail === 'string') return payload.detail;
  if (payload && Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.msg || item?.detail)
      .filter(Boolean)
      .join('; ');
  }
  if (status === 401) return 'Your session has expired. Please sign in again.';
  if (status === 404) return 'The requested recruiter record was not found.';
  if (status >= 500) return 'The backend could not complete this request. Please try again.';
  return `Request failed (${status}).`;
}

async function request(path, options = {}) {
  const { timeout = 8000, headers: extraHeaders, ...fetchOptions } = options;
  const token = getAccessToken();
  const headers = {
    ...(fetchOptions.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extraHeaders,
  };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error('The backend did not respond. Confirm it is running on http://localhost:8000.');
    }
    throw new Error('Unable to reach the backend API.');
  } finally {
    clearTimeout(timer);
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    if (response.status === 401 && token) {
      notifyUnauthorized();
    }
    throw new Error(errorMessage(payload, response.status));
  }
  return payload;
}

export const api = {
  signupRecruiter: ({ full_name, email, password }) =>
    request('/api/v1/auth/recruiter/signup', {
      method: 'POST',
      body: JSON.stringify({ full_name, email, password }),
    }),
  loginRecruiter: ({ email, password }) =>
    request('/api/v1/auth/recruiter/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  getMe: () => request('/api/v1/auth/me'),
  logoutRecruiter: () =>
    request('/api/v1/auth/logout', {
      method: 'POST',
    }),
  forgotPassword: (email) =>
    request('/api/v1/auth/recruiter/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  resetPassword: ({ token, new_password }) =>
    request('/api/v1/auth/recruiter/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password }),
    }),
  listCandidates: () => request('/api/v1/dashboard/candidates'),
  getCandidate: (id) => request(`/api/v1/dashboard/candidates/${id}`),
  listApplications: (eligibleOnly = false) =>
    request(`/api/v1/dashboard/applications${eligibleOnly ? '?eligible_only=true' : ''}`),
  getApplication: (id) => request(`/api/v1/dashboard/applications/${id}`),
  getInterviewResult: (applicationId) =>
    request(`/api/v1/dashboard/applications/${applicationId}/interview-result`),
  listJobs: () => request('/api/v1/dashboard/jobs'),
  getJob: (id) => request(`/api/v1/dashboard/jobs/${id}`),
  createJob: ({ job_title, jd_text, interview_question_count }) =>
    request('/api/v1/dashboard/jobs', {
      method: 'POST',
      body: JSON.stringify({ job_title, jd_text, interview_question_count }),
      timeout: LLM_TIMEOUT_MS,
    }),
  submitApplicationDecision: (applicationId, decision) =>
    request(`/api/v1/dashboard/applications/${applicationId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    }),
  analyzeJd: (jd_text) =>
    request('/analyze-jd', {
      method: 'POST',
      body: JSON.stringify({ jd_text }),
      timeout: LLM_TIMEOUT_MS,
    }),
  listVoiceSessions: () => request('/api/v1/voice/sessions'),
  getVoiceSession: (sessionId) => request(`/api/v1/voice/sessions/${sessionId}`),
  getVoiceSessionStatus: (sessionId) =>
    request(`/api/v1/voice/sessions/${sessionId}/status`),
};
