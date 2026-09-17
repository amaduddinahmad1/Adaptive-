import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PublicOnly, RequireAuth } from '../components/auth/AuthGuards';
import { AuthProvider, useAuth } from '../context/AuthContext';
import LoginPage from '../pages/LoginPage';
import SignupPage from '../pages/SignupPage';
import ForgotPasswordPage from '../pages/ForgotPasswordPage';
import ResetPasswordPage from '../pages/ResetPasswordPage';
import { clearAccessToken, setAccessToken } from '../services/authStorage';

const apiMocks = vi.hoisted(() => ({
  loginRecruiter: vi.fn(),
  signupRecruiter: vi.fn(),
  getMe: vi.fn(),
  logoutRecruiter: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
}));

vi.mock('../services/api', () => ({
  api: apiMocks,
}));

const recruiter = {
  id: 1,
  full_name: 'Alex Mercer',
  email: 'alex@example.com',
  role: 'recruiter',
};

function AuthedHome() {
  const { logout } = useAuth();
  return (
    <div>
      <div>Dashboard home</div>
      <button type="button" onClick={() => logout()}>Sign Out</button>
    </div>
  );
}

function renderAuthApp(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <Routes>
          <Route
            path="/login"
            element={(
              <PublicOnly>
                <LoginPage />
              </PublicOnly>
            )}
          />
          <Route
            path="/signup"
            element={(
              <PublicOnly>
                <SignupPage />
              </PublicOnly>
            )}
          />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route
            path="/"
            element={(
              <RequireAuth>
                <AuthedHome />
              </RequireAuth>
            )}
          />
          <Route
            path="/pipeline"
            element={(
              <RequireAuth>
                <div>Pipeline page</div>
              </RequireAuth>
            )}
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('recruiter authentication UI', () => {
  beforeEach(() => {
    clearAccessToken();
    apiMocks.loginRecruiter.mockReset();
    apiMocks.signupRecruiter.mockReset();
    apiMocks.getMe.mockReset();
    apiMocks.logoutRecruiter.mockReset();
    apiMocks.forgotPassword.mockReset();
    apiMocks.resetPassword.mockReset();
  });

  it('renders the login page', async () => {
    renderAuthApp('/login');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Login' })).toBeInTheDocument();
  });

  it('renders the signup page', async () => {
    renderAuthApp('/signup');
    expect(await screen.findByRole('heading', { name: 'Create recruiter account' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create Recruiter Account' })).toBeInTheDocument();
  });

  it('shows validation errors and does not submit an incomplete login', async () => {
    const user = userEvent.setup();
    renderAuthApp('/login');
    await user.click(await screen.findByRole('button', { name: 'Login' }));
    expect(await screen.findByText('Email is required.')).toBeInTheDocument();
    expect(screen.getByText('Password is required.')).toBeInTheDocument();
    expect(apiMocks.loginRecruiter).not.toHaveBeenCalled();
  });

  it('navigates to the dashboard after a successful login', async () => {
    apiMocks.loginRecruiter.mockResolvedValue({
      access_token: 'test-token',
      token_type: 'bearer',
      recruiter,
    });
    const user = userEvent.setup();
    renderAuthApp('/login');
    await user.type(await screen.findByPlaceholderText('recruiter@company.com'), 'alex@example.com');
    await user.type(screen.getByPlaceholderText('Enter your password'), 'SecurePass1');
    await user.click(screen.getByRole('button', { name: 'Login' }));
    expect(await screen.findByText('Dashboard home')).toBeInTheDocument();
    expect(apiMocks.loginRecruiter).toHaveBeenCalledWith({
      email: 'alex@example.com',
      password: 'SecurePass1',
    });
  });

  it('shows a safe error when login fails', async () => {
    apiMocks.loginRecruiter.mockRejectedValue(new Error('Invalid email or password.'));
    const user = userEvent.setup();
    renderAuthApp('/login');
    await user.type(await screen.findByPlaceholderText('recruiter@company.com'), 'alex@example.com');
    await user.type(screen.getByPlaceholderText('Enter your password'), 'WrongPass1');
    await user.click(screen.getByRole('button', { name: 'Login' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.');
    expect(screen.queryByText('Dashboard home')).not.toBeInTheDocument();
  });

  it('redirects unauthenticated users from protected routes to login', async () => {
    renderAuthApp('/pipeline');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(screen.queryByText('Pipeline page')).not.toBeInTheDocument();
  });

  it('lets an authenticated recruiter open the dashboard', async () => {
    setAccessToken('test-token');
    apiMocks.getMe.mockResolvedValue(recruiter);
    renderAuthApp('/');
    expect(await screen.findByText('Dashboard home')).toBeInTheDocument();
  });

  it('returns to login after logout', async () => {
    setAccessToken('test-token');
    apiMocks.getMe.mockResolvedValue(recruiter);
    apiMocks.logoutRecruiter.mockResolvedValue({ detail: 'Logged out' });
    const user = userEvent.setup();
    renderAuthApp('/');
    await user.click(await screen.findByRole('button', { name: 'Sign Out' }));
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(screen.queryByText('Dashboard home')).not.toBeInTheDocument();
  });

  it('restores the authenticated recruiter after refresh', async () => {
    setAccessToken('persisted-token');
    apiMocks.getMe.mockResolvedValue(recruiter);
    renderAuthApp('/pipeline');
    expect(await screen.findByText('Pipeline page')).toBeInTheDocument();
    expect(apiMocks.getMe).toHaveBeenCalled();
  });

  it('links from login to the forgot password page', async () => {
    const user = userEvent.setup();
    renderAuthApp('/login');
    await user.click(await screen.findByRole('link', { name: 'Forgot password?' }));
    expect(await screen.findByRole('heading', { name: 'Forgot password' })).toBeInTheDocument();
  });

  it('shows a generic forgot-password success message', async () => {
    apiMocks.forgotPassword.mockResolvedValue({
      message: 'If an account exists for that email, a password reset link has been sent.',
    });
    const user = userEvent.setup();
    renderAuthApp('/forgot-password');
    await user.type(await screen.findByPlaceholderText('recruiter@company.com'), 'alex@example.com');
    await user.click(screen.getByRole('button', { name: 'Send Reset Link' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      "If an account exists for that email, we've sent a password reset link.",
    );
    expect(apiMocks.forgotPassword).toHaveBeenCalledWith('alex@example.com');
    expect(screen.queryByText(/account exists for alex@example.com/i)).not.toBeInTheDocument();
  });

  it('does not submit forgot password when email is empty', async () => {
    const user = userEvent.setup();
    renderAuthApp('/forgot-password');
    await user.click(await screen.findByRole('button', { name: 'Send Reset Link' }));
    expect(await screen.findByText('Email is required.')).toBeInTheDocument();
    expect(apiMocks.forgotPassword).not.toHaveBeenCalled();
  });

  it('requires matching passwords on the reset page', async () => {
    const user = userEvent.setup();
    renderAuthApp('/reset-password?token=test-reset-token');
    await user.type(await screen.findByPlaceholderText('At least 8 characters'), 'NewPass99');
    await user.type(screen.getByPlaceholderText('Re-enter password'), 'Mismatch1');
    await user.click(screen.getByRole('button', { name: 'Reset Password' }));
    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument();
    expect(apiMocks.resetPassword).not.toHaveBeenCalled();
  });

  it('rejects a weak password on the reset page without calling the API', async () => {
    const user = userEvent.setup();
    renderAuthApp('/reset-password?token=test-reset-token');
    await user.type(await screen.findByPlaceholderText('At least 8 characters'), 'short');
    await user.type(screen.getByPlaceholderText('Re-enter password'), 'short');
    await user.click(screen.getByRole('button', { name: 'Reset Password' }));
    expect(await screen.findByText('Password must be at least 8 characters.')).toBeInTheDocument();
    expect(apiMocks.resetPassword).not.toHaveBeenCalled();
  });

  it('resets the password and offers a login action', async () => {
    apiMocks.resetPassword.mockResolvedValue({ message: 'Password reset successfully.' });
    const user = userEvent.setup();
    renderAuthApp('/reset-password?token=test-reset-token');
    await user.type(await screen.findByPlaceholderText('At least 8 characters'), 'NewPass99');
    await user.type(screen.getByPlaceholderText('Re-enter password'), 'NewPass99');
    await user.click(screen.getByRole('button', { name: 'Reset Password' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Password reset successfully.');
    expect(screen.getByRole('link', { name: 'Go to Login' })).toBeInTheDocument();
    expect(apiMocks.resetPassword).toHaveBeenCalledWith({
      token: 'test-reset-token',
      new_password: 'NewPass99',
    });
    expect(screen.queryByText('test-reset-token')).not.toBeInTheDocument();
  });

  it('shows a safe message when the reset token is missing', async () => {
    renderAuthApp('/reset-password');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This password reset link is invalid or has expired.',
    );
    expect(apiMocks.resetPassword).not.toHaveBeenCalled();
  });
});
