import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from '../services/authStorage';

const AuthContext = createContext(null);

function isPublicAuthPath(pathname) {
  return (
    pathname.startsWith('/login')
    || pathname.startsWith('/signup')
    || pathname.startsWith('/forgot-password')
    || pathname.startsWith('/reset-password')
  );
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [recruiter, setRecruiter] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAccessToken()));

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setRecruiter(null);
      if (!isPublicAuthPath(location.pathname)) {
        navigate('/login', { replace: true });
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [location.pathname, navigate]);

  useEffect(() => {
    let cancelled = false;
    const token = getAccessToken();
    if (!token) {
      setLoading(false);
      return undefined;
    }
    api
      .getMe()
      .then((payload) => {
        if (!cancelled) setRecruiter(payload);
      })
      .catch(() => {
        clearAccessToken();
        if (!cancelled) setRecruiter(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyAuth = useCallback((payload) => {
    setAccessToken(payload.access_token);
    setRecruiter(payload.recruiter);
    return payload.recruiter;
  }, []);

  const login = useCallback(
    async (email, password) => {
      const payload = await api.loginRecruiter({ email, password });
      return applyAuth(payload);
    },
    [applyAuth],
  );

  const signup = useCallback(
    async ({ full_name, email, password }) => {
      const payload = await api.signupRecruiter({ full_name, email, password });
      return applyAuth(payload);
    },
    [applyAuth],
  );

  const logout = useCallback(async () => {
    try {
      if (getAccessToken()) {
        await api.logoutRecruiter();
      }
    } catch {
      // Client state is cleared regardless of whether the token is still accepted.
    }
    clearAccessToken();
    setRecruiter(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const value = useMemo(
    () => ({ recruiter, loading, login, signup, logout }),
    [recruiter, loading, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return value;
}
