export function ApplicationSuccess({ result, email, onReset }) {
  const invited = result.overall_eligible && result.invitation_sent;
  const eligibleUnsent = result.overall_eligible && !result.invitation_sent;

  let title = 'Application received';
  let body;
  if (invited) {
    title = 'Interview invitation sent';
    body = `Thank you. Your application for ${result.job_title} was eligible for the interview stage. An interview invitation has been sent to ${email}. The link is valid for 48 hours and can be used once.`;
  } else if (eligibleUnsent) {
    title = 'Application received';
    body = `Thank you. Your application for ${result.job_title} was eligible for the interview stage, but the invitation email could not be sent yet. Please watch your inbox or contact the recruiter if it does not arrive.`;
  } else {
    title = 'Application received';
    body = `Thank you for applying to ${result.job_title}. After screening your application against this role, you are not eligible to proceed to the interview stage. No interview invitation has been sent.`;
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-[#131B2F] px-6 py-10 text-center sm:px-8">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl border border-[#C0C1FF]/30 bg-[#C0C1FF]/10 text-[#C0C1FF]">
        {result.overall_eligible ? <CheckIcon /> : <DocIcon />}
      </div>
      <h2 className="font-display text-2xl font-semibold text-white">{title}</h2>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-400">{body}</p>
      <button
        type="button"
        onClick={onReset}
        className="mt-8 text-sm text-[#C0C1FF] underline decoration-[#C0C1FF]/40 underline-offset-4"
      >
        Submit another application
      </button>
    </div>
  );
}

export function ApplicationError({ message, onDismiss }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-left text-sm text-red-100"
    >
      <div className="flex items-start justify-between gap-3">
        <p>{message}</p>
        {onDismiss ? (
          <button type="button" onClick={onDismiss} className="text-red-200/80 hover:text-white">
            Dismiss
          </button>
        ) : null}
      </div>
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M7 3.5h7.5L19 8v12.5H7V3.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M14.5 3.5V8H19" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}
