import { useEffect, useRef } from 'react';

export const inputClass = 'mt-2 w-full rounded-xl border border-[#d5ddd3] bg-white px-4 py-3 text-sm outline-none transition focus:border-[#173b35] focus:ring-2 focus:ring-[#173b35]/10 disabled:bg-slate-50';

export function Button({ children, secondary = false, danger = false, className = '', ...props }) {
  props.type ??= 'button';
  return <button {...props} className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173b35] disabled:cursor-wait disabled:opacity-50 ${danger ? 'border border-red-200 bg-red-50 text-red-700 hover:bg-red-100' : secondary ? 'border border-[#d5ddd3] bg-white text-[#173b35] hover:bg-slate-50' : 'bg-[#173b35] text-white hover:bg-[#265248]'} ${className}`}>{children}</button>;
}

export function Field({ label, children, ...props }) {
  return <label className="block text-sm font-medium">{label}{children || <input {...props} className={inputClass} />}</label>;
}

export function Alert({ error, message }) {
  return error ? <p role="alert" className="my-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p> : message ? <p role="status" className="my-4 rounded-xl bg-green-50 p-4 text-sm text-green-800">{message}</p> : null;
}

export function Badge({ children }) {
  return <span className="inline-flex rounded-full bg-[#edf2e9] px-2.5 py-1 text-xs font-medium capitalize">{children}</span>;
}

export function Modal({ title, children, onClose }) {
  const dialog = useRef(null);
  useEffect(() => { dialog.current.showModal(); }, []);
  return <dialog ref={dialog} onCancel={event => { event.preventDefault(); onClose(); }} className="fixed inset-0 m-auto max-h-[90vh] w-[min(92vw,520px)] overflow-auto rounded-2xl border-0 bg-white p-6 text-[#173b35] shadow-xl backdrop:bg-black/30" aria-labelledby="modal-title">
    <div className="mb-5 flex items-center justify-between gap-4"><h2 id="modal-title" className="text-xl font-semibold">{title}</h2><button aria-label="Close dialog" onClick={onClose} className="rounded-lg px-3 py-1 text-xl hover:bg-slate-100">×</button></div>{children}
  </dialog>;
}

export function Pagination({ page, total, limit = 20, onChange }) {
  return <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500"><span>{total} results · Page {page} of {Math.max(1, Math.ceil(total / limit))}</span><div className="flex gap-2"><Button secondary disabled={page === 1} onClick={() => onChange(page - 1)}>Previous</Button><Button secondary disabled={page * limit >= total} onClick={() => onChange(page + 1)}>Next</Button></div></div>;
}

export function PageHeader({ title, description, children }) {
  return <header className="mb-7 flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm leading-6 text-slate-500">{description}</p></div><div className="flex flex-wrap gap-2">{children}</div></header>;
}

export const tableClass = 'w-full text-left text-sm [&_th]:whitespace-nowrap [&_th]:border-b [&_th]:border-slate-200 [&_th]:px-4 [&_th]:py-3 [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wider [&_th]:text-slate-500 [&_td]:border-b [&_td]:border-slate-100 [&_td]:px-4 [&_td]:py-4';
