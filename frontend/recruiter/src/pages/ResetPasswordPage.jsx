import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthShell, { AuthField, authButtonClassName, authInputClassName } from '../components/auth/AuthShell';
import { api } from '../services/api';

const INVALID_LINK_MESSAGE = 'This password reset link is invalid or has expired.';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = (searchParams.get('token') || '').trim();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState(false);

  const errors = useMemo(() => {
    const next = {};
    if (password.length < 8) next.password = 'Password must be at least 8 characters.';
    else if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      next.password = 'Password must include at least one letter and one number.';
    }
    if (confirmPassword !== password) next.confirmPassword = 'Passwords do not match.';
    return next;
  }, [password, confirmPassword]);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitted(true);
    setFormError('');
    if (!token) {
      setFormError(INVALID_LINK_MESSAGE);
      return;
    }
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      await api.resetPassword({ token, new_password: password });
      setSuccess(true);
    } catch (err) {
      const message = err?.message || '';
      if (message.toLowerCase().includes('password must')) {
        setFormError(message);
      } else if (message.includes('Invalid or expired')) {
        setFormError(INVALID_LINK_MESSAGE);
      } else {
        setFormError('Unable to reset the password. The link may be invalid or expired.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      kicker="Recruiter access"
      title="Reset password"
      subtitle="Choose a new password for your recruiter account."
      footer={
        <>
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
            Password reset successfully. Sign in with your new password.
          </p>
          <Link to="/login" className={`${authButtonClassName} text-center`}>
            Go to Login
          </Link>
        </div>
      ) : !token ? (
        <div className="grid gap-4">
          <p className="rounded-[10px] border border-red/30 bg-red-dim px-3 py-2 text-sm text-red" role="alert">
            {INVALID_LINK_MESSAGE}
          </p>
          <Link to="/forgot-password" className="text-center text-sm font-semibold text-lavender-200">
            Request a new reset link
          </Link>
        </div>
      ) : (
        <form className="grid gap-4" onSubmit={submit} noValidate>
          <AuthField label="New Password" error={submitted ? errors.password : null}>
            <input
              className={authInputClassName}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="At least 8 characters"
            />
          </AuthField>
          <AuthField label="Confirm New Password" error={submitted ? errors.confirmPassword : null}>
            <input
              className={authInputClassName}
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Re-enter password"
            />
          </AuthField>
          {formError ? (
            <p className="rounded-[10px] border border-red/30 bg-red-dim px-3 py-2 text-sm text-red" role="alert">
              {formError}
            </p>
          ) : null}
          <button type="submit" className={authButtonClassName} disabled={loading}>
            {loading ? 'Resetting password…' : 'Reset Password'}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
