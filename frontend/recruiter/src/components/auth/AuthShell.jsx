import { Link } from 'react-router-dom';

export function AuthBrandMark() {
  return (
    <span
      className="grid h-[34px] w-[34px] place-items-center rounded-[10px] bg-gradient-to-br from-lavender-200 to-lavender-600 shadow-[0_0_0_4px_rgba(192,193,255,0.08)]"
      aria-hidden="true"
    >
      <span className="h-3 w-3 rounded bg-navy-950" />
    </span>
  );
}

export default function AuthShell({
  kicker,
  title,
  subtitle,
  children,
  footer,
}) {
  return (
    <div className="min-h-screen overflow-x-hidden bg-navy-950 bg-[radial-gradient(1200px_600px_at_80%_-10%,rgba(139,141,255,0.08),transparent_50%)] text-ink">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl items-center gap-10 px-4 py-10 md:grid-cols-2 md:px-8 lg:gap-16">
        <div className="max-w-md">
          <Link to="/login" className="mb-8 inline-flex items-center gap-3 text-ink">
            <AuthBrandMark />
            <span>
              <span className="block text-base font-bold tracking-[-0.02em]">InterviewAI</span>
              <span className="block text-[11px] text-ink-muted">Enterprise Tier</span>
            </span>
          </Link>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">{kicker}</p>
          <h1 className="mt-3 text-[28px] font-bold tracking-[-0.03em] text-ink md:text-[34px]">
            AI Interview Platform
          </h1>
          <p className="mt-3 max-w-sm text-sm text-ink-secondary">
            Access the recruiter workspace to manage jobs, candidate pipeline, live sessions, and
            assessment reports.
          </p>
        </div>

        <div className="w-full max-w-md justify-self-center md:justify-self-end">
          <div className="rounded-[16px] border border-line bg-navy-800 p-6 shadow-panel sm:p-8">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink-muted">{kicker}</p>
            <h2 className="mt-2 text-2xl font-bold tracking-[-0.03em]">{title}</h2>
            <p className="mt-1 text-sm text-ink-secondary">{subtitle}</p>
            <div className="mt-6">{children}</div>
          </div>
          {footer ? <div className="mt-4 text-center text-sm text-ink-secondary">{footer}</div> : null}
        </div>
      </div>
    </div>
  );
}

export function AuthField({ label, error, children }) {
  return (
    <label className="grid gap-2">
      <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink-muted">{label}</span>
      {children}
      {error ? <span className="text-xs text-red">{error}</span> : null}
    </label>
  );
}

export const authInputClassName =
  'w-full rounded-[10px] border border-line bg-[#0e1629] px-3 py-[11px] text-[13px] text-ink outline-none placeholder:text-ink-muted focus:border-lavender-400';

export const authButtonClassName =
  'w-full rounded-[11px] bg-lavender-300 px-4 py-3 text-sm font-semibold text-navy-950 transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-55';
