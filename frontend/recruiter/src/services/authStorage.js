const TOKEN_KEY = 'recruiter_access_token';

let unauthorizedHandler = null;

export function getAccessToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function notifyUnauthorized() {
  clearAccessToken();
  if (typeof unauthorizedHandler === 'function') {
    unauthorizedHandler();
  }
}
