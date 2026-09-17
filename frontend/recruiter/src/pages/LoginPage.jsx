import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import AuthShell, { AuthField, authButtonClassName, authInputClassName } from '../components/auth/AuthShell';
import { useAuth } from '../context/AuthContext';

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');

  const errors = useMemo(() => {
    const next = {};
    if (!email.trim()) next.email = 'Email is required.';
    else if (!isValidEmail(email.trim())) next.email = 'Enter a valid email address.';
    if (!password) next.password = 'Password is required.';
    return next;
  }, [email, password]);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitted(true);
    setFormError('');
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      await login(email.trim(), password);
      const destination = location.state?.from?.pathname || '/';
      navigate(destination, { replace: true });
    } catch (err) {
      setFormError(err.message || 'Unable to sign in. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      kicker="Recruiter access"
      title="Welcome back"
      subtitle="Sign in to continue to the InterviewAI recruiter dashboard."
      footer={
        <>
          Don&apos;t have an account?{' '}
          <Link to="/signup" className="font-semibold text-lavender-200">
            Sign Up
          </Link>
        </>
      }
    >
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <AuthField label="Email" error={submitted ? errors.email : null}>
          <input
            className={authInputClassName}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="recruiter@company.com"
          />
        </AuthField>
        <AuthField label="Password" error={submitted ? errors.password : null}>
          <input
            className={authInputClassName}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter your password"
          />
        </AuthField>
        <div className="flex justify-end">
          <Link
            to="/forgot-password"
            className="text-xs font-medium text-lavender-200/70 hover:text-lavender-200"
          >
            Forgot password?
          </Link>
        </div>
        {formError ? (
          <p className="rounded-[10px] border border-red/30 bg-red-dim px-3 py-2 text-sm text-red" role="alert">
            {formError}
          </p>
        ) : null}
        <button type="submit" className={authButtonClassName} disabled={loading}>
          {loading ? 'Signing in…' : 'Login'}
        </button>
      </form>
    </AuthShell>
  );
}
