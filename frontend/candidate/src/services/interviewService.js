const API_BASE = 'http://localhost:8000/api/v1';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      `Voice API ${response.status}: ${detail || response.statusText}`,
    );
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const createSession = async (
  candidateId,
  jobId = 'demo-job',
  language = 'en',
) => {
  return request('/voice/sessions', {
    method: 'POST',
    body: JSON.stringify({
      candidate_id: candidateId,
      job_id: jobId,
      language,
    }),
  });
};

export const startInterview = async (sessionId, candidateId) => {
  const query = candidateId
    ? `?candidate=${encodeURIComponent(candidateId)}`
    : '';
  return request(`/voice/sessions/${encodeURIComponent(sessionId)}/start${query}`, {
    method: 'POST',
  });
};

export const endInterview = async (sessionId, extra) => {
  return request(`/voice/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: 'POST',
    ...(extra ? { body: JSON.stringify(extra) } : {}),
  });
};

export const getSession = async (sessionId) => {
  return request(`/voice/sessions/${encodeURIComponent(sessionId)}/status`);
};
