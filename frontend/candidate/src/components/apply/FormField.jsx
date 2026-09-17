const lightControl =
  'w-full rounded-md border border-transparent bg-white px-3 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-[#C0C1FF]/70 disabled:cursor-not-allowed disabled:opacity-70';

const darkControl =
  'w-full rounded-md border border-white/10 bg-[#0B1326] px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-[#C0C1FF]/40 disabled:cursor-not-allowed disabled:opacity-70';

export default function FormField({
  id,
  label,
  name,
  type = 'text',
  value,
  onChange,
  placeholder,
  required = false,
  error,
  disabled = false,
  as = 'input',
  prefix,
  variant = 'light',
  children,
}) {
  const controlClass = variant === 'dark' ? darkControl : lightControl;
  const describedBy = error ? `${id}-error` : undefined;

  let control;
  if (as === 'select') {
    control = (
      <select
        id={id}
        name={name}
        value={value}
        onChange={onChange}
        required={required}
        disabled={disabled}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`${controlClass} appearance-none bg-[length:1rem] bg-[right_0.75rem_center] bg-no-repeat pr-10`}
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' viewBox='0 0 24 24'%3E%3Cpath stroke='%2394a3b8' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
        }}
      >
        {children}
      </select>
    );
  } else if (as === 'textarea') {
    control = (
      <textarea
        id={id}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        rows={4}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`${controlClass} min-h-[6.5rem] resize-y`}
      />
    );
  } else if (prefix) {
    control = (
      <div className={`flex items-center ${variant === 'light' ? 'rounded-md bg-white' : 'rounded-md bg-[#0B1326] border border-white/10'}`}>
        <span className={`pl-3 text-sm ${variant === 'light' ? 'text-slate-400' : 'text-slate-500'}`}>
          {prefix}
        </span>
        <input
          id={id}
          name={name}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          className="w-full rounded-md border-0 bg-transparent px-2 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:ring-0 disabled:cursor-not-allowed"
        />
      </div>
    );
  } else {
    control = (
      <input
        id={id}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={controlClass}
      />
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">
        {label}
      </label>
      {control}
      {error ? (
        <span id={`${id}-error`} className="text-xs text-red-300">
          {error}
        </span>
      ) : null}
    </div>
  );
}
