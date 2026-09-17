import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export function AuthLoadingScreen({ label = 'Restoring session' }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 text-[13px] text-ink-secondary">
      <div className="flex items-center gap-2.5">
        <span className="h-[18px] w-[18px] animate-spin rounded-full border-2 border-navy-600 border-t-lavender-300" />
        <span>{label}…</span>
      </div>
    </div>
  );
}

export function RequireAuth({ children }) {
  const { recruiter, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <AuthLoadingScreen />;
  }
  if (!recruiter) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}

export function PublicOnly({ children }) {
  const { recruiter, loading } = useAuth();
  if (loading) {
    return <AuthLoadingScreen />;
  }
  if (recruiter) {
    return <Navigate to="/" replace />;
  }
  return children;
}
