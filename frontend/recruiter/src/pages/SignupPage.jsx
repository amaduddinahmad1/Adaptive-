import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell, { AuthField, authButtonClassName, authInputClassName } from '../components/auth/AuthShell';
import { useAuth } from '../context/AuthContext';

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');

  const errors = useMemo(() => {
    const next = {};
    if (fullName.trim().length < 2) next.fullName = 'Full name is required.';
    if (!email.trim()) next.email = 'Email is required.';
    else if (!isValidEmail(email.trim())) next.email = 'Enter a valid email address.';
    if (password.length < 8) next.password = 'Password must be at least 8 characters.';
    else if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      next.password = 'Password must include at least one letter and one number.';
    }
    if (confirmPassword !== password) next.confirmPassword = 'Passwords do not match.';
    return next;
  }, [fullName, email, password, confirmPassword]);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitted(true);
    setFormError('');
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      await signup({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      navigate('/', { replace: true });
    } catch (err) {
      setFormError(err.message || 'Unable to create the recruiter account. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      kicker="Recruiter access"
      title="Create recruiter account"
      subtitle="Register to access the InterviewAI recruiter dashboard."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-lavender-200">
            Login
          </Link>
        </>
      }
    >
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <AuthField label="Full Name" error={submitted ? errors.fullName : null}>
          <input
            className={authInputClassName}
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Alex Mercer"
          />
        </AuthField>
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
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 8 characters"
          />
        </AuthField>
        <AuthField label="Confirm Password" error={submitted ? errors.confirmPassword : null}>
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
          {loading ? 'Creating account…' : 'Create Recruiter Account'}
        </button>
      </form>
    </AuthShell>
  );
}
