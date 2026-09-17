export default function SubmitButton({ loading = false, disabled = false, children }) {
  return (
    <button
      type="submit"
      disabled={disabled || loading}
      className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#C0C1FF] px-4 py-3 text-sm font-semibold text-[#1B2150] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {loading ? (
        <span
          className="size-4 animate-spin rounded-full border-2 border-[#1B2150]/30 border-t-[#1B2150]"
          aria-hidden="true"
        />
      ) : null}
      <span>{loading ? 'Submitting application…' : children}</span>
    </button>
  );
}
