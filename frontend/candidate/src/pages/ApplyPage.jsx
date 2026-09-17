import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import FormField from '../components/apply/FormField';
import FileUpload from '../components/apply/FileUpload';
import SubmitButton from '../components/apply/SubmitButton';
import { ApplicationError, ApplicationSuccess } from '../components/apply/ApplicationResult';
import { listOpenJobs, submitApplication } from '../services/applicationService';

const AVAILABILITY_OPTIONS = [
  { value: 'immediate', label: 'Immediate' },
  { value: '2 weeks', label: '2 weeks' },
  { value: '1 month', label: '1 month' },
  { value: '2 months', label: '2 months' },
  { value: '3 months', label: '3 months' },
];

const EMPTY_FORM = {
  fullName: '',
  email: '',
  phone: '',
  jobId: '',
  salary: '',
  availability: '',
};

function parseSalary(value) {
  const numeric = String(value).replace(/,/g, '').trim();
  if (!numeric) return null;
  const amount = Number(numeric);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return amount;
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function ApplyPage() {
  const { jobId: jobIdParam } = useParams();

  useEffect(() => {
    document.title = 'Candidate Application Form';
  }, []);

  const [jobs, setJobs] = useState([]);
  const [jobsError, setJobsError] = useState('');
  const [jobsLoading, setJobsLoading] = useState(true);
  const [form, setForm] = useState({ ...EMPTY_FORM, jobId: jobIdParam || '' });
  const [cvFile, setCvFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [result, setResult] = useState(null);

  const loadJobs = () => {
    setJobsLoading(true);
    setJobsError('');
    listOpenJobs()
      .then((payload) => {
        setJobs(Array.isArray(payload) ? payload : []);
      })
      .catch(() => {
        setJobsError('Open roles could not be loaded. Please try again.');
        setJobs([]);
      })
      .finally(() => setJobsLoading(false));
  };

  useEffect(() => {
    listOpenJobs()
      .then((payload) => {
        setJobs(Array.isArray(payload) ? payload : []);
      })
      .catch(() => {
        setJobsError('Open roles could not be loaded. Please try again.');
        setJobs([]);
      })
      .finally(() => setJobsLoading(false));
  }, []);

  const selectedJob = useMemo(
    () => jobs.find((job) => String(job.id) === String(form.jobId)),
    [jobs, form.jobId],
  );

  const setField = (name) => (event) => {
    const value = event.target.value;
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: '' }));
  };

  const validate = () => {
    const next = {};
    if (!form.fullName.trim()) next.fullName = 'Enter your full name.';
    if (!form.email.trim()) next.email = 'Enter your email address.';
    else if (!isValidEmail(form.email.trim())) next.email = 'Enter a valid email address.';
    if (!form.phone.trim()) next.phone = 'Enter your phone number.';
    if (!form.jobId) next.jobId = 'Select the role you are applying for.';
    else if (jobs.length && !selectedJob) next.jobId = 'Select a current open role.';
    const salary = parseSalary(form.salary);
    if (salary == null) next.salary = 'Enter your expected salary.';
    if (!form.availability) next.availability = 'Select your notice period / availability.';
    if (!cvFile) next.cv = 'Upload your resume as a PDF or DOCX file.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitError('');
    if (!validate() || submitting) return;
    setSubmitting(true);
    try {
      const payload = await submitApplication({
        jobId: form.jobId,
        fullName: form.fullName.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        joiningAvailability: form.availability,
        salaryExpectation: parseSalary(form.salary),
        cvFile,
      });
      setResult(payload);
    } catch (err) {
      setSubmitError(err.message || 'Your application could not be submitted. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setForm({ ...EMPTY_FORM, jobId: jobIdParam || '' });
    setCvFile(null);
    setErrors({});
    setSubmitError('');
    setResult(null);
  };

  return (
    <div className="relative isolate min-h-screen bg-[#0B1326] px-4 py-10 font-sans text-slate-200 sm:px-6 sm:py-16">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(ellipse_at_top,rgba(192,193,255,0.12),transparent_60%)]" />
      <div className="relative mx-auto flex w-full max-w-[640px] flex-col items-center">
        <div className="mb-6 flex size-12 items-center justify-center rounded-xl border border-[#C0C1FF]/25 bg-[#C0C1FF]/10 text-[#C0C1FF]">
          <UserIcon />
        </div>
        <h1 className="text-center font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Join the AI Revolution
        </h1>
        <p className="mt-3 max-w-md text-center text-sm leading-relaxed text-slate-400">
          Submit your application below. Our sophisticated AI models will analyze your profile to find the perfect role fit.
        </p>

        <div className="mt-8 w-full">
          {result ? (
            <ApplicationSuccess result={result} email={form.email.trim()} onReset={reset} />
          ) : (
            <form
              onSubmit={onSubmit}
              className="rounded-2xl border border-white/10 bg-[#131B2F] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.35)] sm:p-8"
              noValidate
            >
              <Section title="Personal Information" icon={<UserSmallIcon />}>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <FormField
                    id="fullName"
                    label="Full name"
                    name="fullName"
                    value={form.fullName}
                    onChange={setField('fullName')}
                    placeholder="Jane Doe"
                    required
                    disabled={submitting}
                    error={errors.fullName}
                  />
                  <FormField
                    id="email"
                    label="Email address"
                    name="email"
                    type="email"
                    value={form.email}
                    onChange={setField('email')}
                    placeholder="jane@example.com"
                    required
                    disabled={submitting}
                    error={errors.email}
                  />
                </div>
                <FormField
                  id="phone"
                  label="Phone number"
                  name="phone"
                  type="tel"
                  value={form.phone}
                  onChange={setField('phone')}
                  placeholder="+1 (555) 000-0000"
                  required
                  disabled={submitting}
                  error={errors.phone}
                />
              </Section>

              <Section title="Professional Details" icon={<BriefcaseIcon />}>
                <FormField
                  id="jobId"
                  label="Position"
                  name="jobId"
                  as="select"
                  variant="dark"
                  value={form.jobId}
                  onChange={setField('jobId')}
                  required
                  disabled={submitting || jobsLoading}
                  error={errors.jobId}
                >
                  <option value="">
                    {jobsLoading ? 'Loading open roles…' : 'Select the role you are applying for'}
                  </option>
                  {jobs.map((job) => (
                    <option key={job.id} value={String(job.id)}>
                      {job.job_title}
                    </option>
                  ))}
                </FormField>
                {!jobsLoading && !jobsError && jobs.length === 0 ? (
                  <p className="text-xs text-slate-400">
                    There are no open roles to apply for right now.
                  </p>
                ) : null}
                {jobsError ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs text-red-300">{jobsError}</p>
                    <button type="button" onClick={loadJobs} className="self-start text-xs text-[#C0C1FF] underline underline-offset-2">
                      Retry loading roles
                    </button>
                  </div>
                ) : null}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <FormField
                    id="salary"
                    label="Expected salary"
                    name="salary"
                    value={form.salary}
                    onChange={setField('salary')}
                    placeholder="120,000"
                    prefix="$"
                    required
                    disabled={submitting}
                    error={errors.salary}
                  />
                  <FormField
                    id="availability"
                    label="Notice period / availability"
                    name="availability"
                    as="select"
                    variant="dark"
                    value={form.availability}
                    onChange={setField('availability')}
                    required
                    disabled={submitting}
                    error={errors.availability}
                  >
                    <option value="">Select availability...</option>
                    {AVAILABILITY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </FormField>
                </div>
              </Section>

              <Section title="Resume / CV Upload" icon={<DocIcon />}>
                <FileUpload
                  file={cvFile}
                  disabled={submitting}
                  error={errors.cv}
                  onChange={(file, fileError) => {
                    setCvFile(file);
                    setErrors((current) => ({ ...current, cv: fileError }));
                  }}
                />
                <div className="flex gap-3 rounded-xl border border-white/10 bg-[#0B1326]/70 px-4 py-3">
                  <span className="mt-0.5 text-[#C0C1FF]">
                    <SparkleIcon />
                  </span>
                  <div>
                    <p className="text-sm font-medium text-[#C0C1FF]">AI Analysis Enabled</p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-400">
                      Your CV will be analyzed by our AI for job eligibility, extracting key skills and matching them against our open roles.
                    </p>
                  </div>
                </div>
              </Section>

              {submitError ? <ApplicationError message={submitError} onDismiss={() => setSubmitError('')} /> : null}

              <SubmitButton loading={submitting} disabled={jobsLoading || jobs.length === 0}>
                Submit Application →
              </SubmitButton>
            </form>
          )}
        </div>

        <p className="mt-8 text-center text-[11px] leading-relaxed text-slate-500">
          © 2024 IntervueAI Enterprise. All rights reserved.
          <br />
          Privacy Policy • Terms of Service
        </p>
      </div>
    </div>
  );
}

function Section({ title, icon, children }) {
  return (
    <section className="mb-8">
      <h2 className="mb-4 flex items-center gap-2 text-base font-semibold text-white">
        <span className="text-slate-400">{icon}</span>
        {title}
      </h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

function UserIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.25" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5.5 18.5c1.4-3 3.7-4.5 6.5-4.5s5.1 1.5 6.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function UserSmallIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.25" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5.5 18.5c1.4-3 3.7-4.5 6.5-4.5s5.1 1.5 6.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function BriefcaseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="8" width="17" height="11.5" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 8V6.8A1.8 1.8 0 0 1 10.8 5h2.4A1.8 1.8 0 0 1 15 6.8V8" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M7 3.5h7.5L19 8v12.5H7V3.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M14.5 3.5V8H19M9 12h6M9 15.5h6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3.5 13.2 8.8 18.5 10 13.2 11.2 12 16.5 10.8 11.2 5.5 10 10.8 8.8 12 3.5Z" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
