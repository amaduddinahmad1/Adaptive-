import { useRef, useState } from 'react';

const ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document';

export default function FileUpload({
  id = 'cv-upload',
  file,
  onChange,
  error,
  disabled = false,
  maxBytes = 10 * 1024 * 1024,
}) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const validateAndSet = (nextFile) => {
    if (!nextFile) {
      onChange(null, '');
      return;
    }
    const name = nextFile.name.toLowerCase();
    const allowed = name.endsWith('.pdf') || name.endsWith('.docx');
    if (!allowed) {
      onChange(null, 'Please upload a PDF or DOCX resume.');
      return;
    }
    if (nextFile.size > maxBytes) {
      onChange(null, 'The resume must be 10 MB or smaller.');
      return;
    }
    onChange(nextFile, '');
  };

  const onDrop = (event) => {
    event.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const nextFile = event.dataTransfer.files?.[0];
    validateAndSet(nextFile);
  };

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        disabled={disabled}
        onChange={(event) => validateAndSet(event.target.files?.[0])}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        aria-describedby={error ? `${id}-error` : `${id}-hint`}
        className={`flex w-full flex-col items-center justify-center rounded-xl border border-dashed px-4 py-10 text-center transition-colors ${
          dragOver
            ? 'border-[#C0C1FF] bg-[#C0C1FF]/10'
            : 'border-white/15 bg-[#0B1326]/60 hover:border-white/25'
        } disabled:cursor-not-allowed disabled:opacity-70`}
      >
        <span className="mb-3 flex size-10 items-center justify-center rounded-lg bg-white/5 text-[#C0C1FF]">
          <CloudIcon />
        </span>
        <span className="text-sm font-medium text-white">
          {file ? file.name : 'Drag & drop your resume here'}
        </span>
        <span className="mt-1 text-sm text-slate-400">
          {file ? `${Math.max(file.size / (1024 * 1024), 0.01).toFixed(2)} MB · click to replace` : (
            <>
              or <span className="text-slate-200 underline decoration-slate-500 underline-offset-2">browse files</span>
            </>
          )}
        </span>
        <span id={`${id}-hint`} className="mt-3 text-[11px] text-slate-500">
          Supported formats: PDF, DOCX (Max 10MB)
        </span>
      </button>
      {error ? (
        <span id={`${id}-error`} className="text-xs text-red-300">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function CloudIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7.5 18h9.25A3.75 3.75 0 0 0 20.5 12.8a4.5 4.5 0 0 0-8.3-2.45A3.75 3.75 0 0 0 7.5 18Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M12 14.5V9.5m0 0 2.25 2.25M12 9.5 9.75 11.75"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
