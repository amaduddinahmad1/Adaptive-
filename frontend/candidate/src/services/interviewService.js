const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const DEFAULT_TIMEOUT_MS = 20000;
const START_TIMEOUT_MS = 60000;

function errorMessage(payload, status) {
  if (payload && typeof payload.detail === 'string') return payload.detail;
  if (payload && Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.msg || item?.detail)
      .filter(Boolean)
      .join('; ');
  }
  if (status === 404) return 'This interview session was not found.';
  if (status === 409) return 'This interview cannot be started right now.';
  if (status >= 500) return 'The interview session is unavailable right now.';
  return 'The interview request could not be completed. Please try again.';
}

async function request(path, { timeout = DEFAULT_TIMEOUT_MS, ...options } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
      signal: controller.signal,
    });
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error('The interview service did not respond. Please try again in a moment.');
    }
    throw new Error('Unable to reach the interview service. Confirm the backend is running.');
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
    throw new Error(errorMessage(payload, response.status));
  }

  if (response.status === 204) {
    return null;
  }

  return payload;
}

export const createSession = async (applicationId, language = 'en') => {
  return request('/api/v1/voice/sessions', {
    method: 'POST',
    body: JSON.stringify({
      application_id: applicationId,
      language,
    }),
  });
};

export const startInterview = async (sessionId) => {
  return request(`/api/v1/voice/sessions/${encodeURIComponent(sessionId)}/start`, {
    method: 'POST',
    timeout: START_TIMEOUT_MS,
  });
};

export const endInterview = async (sessionId, extra) => {
  return request(`/api/v1/voice/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: 'POST',
    ...(extra ? { body: JSON.stringify(extra) } : {}),
  });
};

export const getSession = async (sessionId) => {
  return request(`/api/v1/voice/sessions/${encodeURIComponent(sessionId)}/status`);
};

export const getSessionDetails = async (sessionId) => {
  return request(`/api/v1/voice/sessions/${encodeURIComponent(sessionId)}`);
};
