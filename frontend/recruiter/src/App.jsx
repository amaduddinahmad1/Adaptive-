import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { PublicOnly, RequireAuth } from './components/auth/AuthGuards';
import RecruiterLayout from './components/layout/RecruiterLayout';
import { AuthProvider } from './context/AuthContext';
import DashboardPage from './pages/DashboardPage';
import PipelinePage from './pages/CandidatesPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import AssessmentReportPage from './pages/AssessmentReportPage';
import JobsPage, { JobCreatePage } from './pages/JobsPage';
import LiveSessionsPage, { LiveSessionDetailPage } from './pages/LiveSessionsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
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
            element={(
              <RequireAuth>
                <RecruiterLayout />
              </RequireAuth>
            )}
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/pipeline/:applicationId" element={<CandidateDetailPage />} />
            <Route path="/pipeline/:applicationId/assessment" element={<AssessmentReportPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/new" element={<JobCreatePage />} />
            <Route path="/jobs/:jobId" element={<JobsPage />} />
            <Route path="/sessions" element={<LiveSessionsPage />} />
            <Route path="/sessions/:sessionId" element={<LiveSessionDetailPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/candidates" element={<Navigate to="/pipeline" replace />} />
            <Route path="/reports" element={<Navigate to="/analytics" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
