import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import InstructionsPage from './InstructionsPage';
import InterviewPage from './InterviewPage';
import InterviewCompletedPage from './InterviewCompletedPage';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { resolveInterviewInvitation } from '../services/applicationService';

export default function InterviewFlow() {
  const { token } = useParams();
  const [currentPage, setCurrentPage] = useState('instructions'); // instructions, interview, completed
  const [invitation, setInvitation] = useState(null);
  const [inviteError, setInviteError] = useState(
    token ? '' : 'This interview invitation is invalid.',
  );
  const [inviteLoading, setInviteLoading] = useState(Boolean(token));

  const navigateTo = (page) => {
    setCurrentPage(page);
  };

  useEffect(() => {
    if (!token) {
      return undefined;
    }

    let cancelled = false;
    resolveInterviewInvitation(token)
      .then((payload) => {
        if (!cancelled) {
          setInvitation(payload);
          setInviteError('');
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setInvitation(null);
          setInviteError(err.message || 'This interview invitation is invalid.');
        }
      })
      .finally(() => {
        if (!cancelled) setInviteLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (inviteLoading) {
    return (
      <div className="app-container">
        <div className="relative isolate flex min-h-screen flex-1 flex-col items-center justify-center bg-ink">
          <LoadingSpinner size="lg" />
        </div>
      </div>
    );
  }

  if (inviteError || !invitation) {
    return (
      <div className="app-container">
        <div className="relative isolate flex min-h-screen flex-1 flex-col items-center justify-center bg-ink px-8">
          <EmptyState
            title="Interview unavailable"
            description={inviteError || 'This interview invitation is invalid.'}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {currentPage === 'instructions' && (
        <InstructionsPage onStart={() => navigateTo('interview')} />
      )}
      {currentPage === 'interview' && (
        <InterviewPage
          applicationId={invitation.application_id}
          candidateName={invitation.candidate_full_name}
          jobTitle={invitation.job_title}
          onComplete={() => navigateTo('completed')}
        />
      )}
      {currentPage === 'completed' && (
        <InterviewCompletedPage />
      )}
    </div>
  );
}
