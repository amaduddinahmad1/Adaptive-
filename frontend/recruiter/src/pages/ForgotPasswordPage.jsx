import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import AuthShell, { AuthField, authButtonClassName, authInputClassName } from '../components/auth/AuthShell';
import { api } from '../services/api';

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

const GENERIC_SUCCESS =
  "If an account exists for that email, we've sent a password reset link.";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState(false);

  const errors = useMemo(() => {
    const next = {};
    if (!email.trim()) next.email = 'Email is required.';
    else if (!isValidEmail(email.trim())) next.email = 'Enter a valid email address.';
    return next;
  }, [email]);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitted(true);
    setFormError('');
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      await api.forgotPassword(email.trim());
      setSuccess(true);
    } catch {
      setFormError('Unable to send a password reset link right now. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      kicker="Recruiter access"
      title="Forgot password"
      subtitle="Enter the email on your recruiter account and we'll send a reset link if it exists."
      footer={
        <>
          Remembered your password?{' '}
          <Link to="/login" className="font-semibold text-lavender-200">
            Back to Login
          </Link>
        </>
      }
    >
      {success ? (
        <div className="grid gap-4">
          <p
            className="rounded-[10px] border border-lavender-400/30 bg-navy-750 px-3 py-2 text-sm text-lavender-200"
            role="status"
          >
            {GENERIC_SUCCESS}
          </p>
          <Link to="/login" className={`${authButtonClassName} text-center`}>
            Back to Login
          </Link>
        </div>
      ) : (
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
          {formError ? (
            <p className="rounded-[10px] border border-red/30 bg-red-dim px-3 py-2 text-sm text-red" role="alert">
              {formError}
            </p>
          ) : null}
          <button type="submit" className={authButtonClassName} disabled={loading}>
            {loading ? 'Sending reset link…' : 'Send Reset Link'}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
