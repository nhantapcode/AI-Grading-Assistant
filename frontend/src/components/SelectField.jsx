/** Native keyboard interactions with a consistently spaced decorative chevron. */
export default function SelectField({ label, children, className = '', ...props }) {
  return <label className={`block text-sm font-medium ${className}`}>
    {label}
    <span className="relative mt-2 block">
      <select {...props} className="w-full appearance-none rounded-xl border border-[#d5ddd3] bg-white py-3.5 pl-4 pr-12 text-sm text-[#173b35] outline-none transition hover:border-[#9bac9f] focus:border-[#173b35] focus:ring-2 focus:ring-[#173b35]/10 disabled:cursor-wait disabled:opacity-60">
        {children}
      </select>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" className="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-[#6c8579]">
        <path d="m7 10 5 5 5-5" />
      </svg>
    </span>
  </label>;
}
