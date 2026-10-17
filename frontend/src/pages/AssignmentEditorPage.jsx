import { useEffect, useState } from 'react';
import { api, post } from '../lib/api';
import FileUpload from '../components/FileUpload';
import { Alert, Button, Field, inputClass, PageHeader } from '../components/ui';

const initial = { title: '', description: '', instructions: '', max_score: 100, exemplar_threshold_percent: 80,
  criteria: [{ title: 'Overall quality', description: '', max_points: 100 }], references: [{ title: 'Answer key', answer_text: '', files: [] }], files: [] };

export default function AssignmentEditorPage({ organization, assignmentId, versionId, navigate, onDirty }) {
  const base = `organizations/${organization.id}`;
  const [activeId, setActiveId] = useState(assignmentId);
  const [activeVersion, setActiveVersion] = useState(versionId);
  const [form, setForm] = useState(initial);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(Boolean(assignmentId));
  const [busy, setBusy] = useState(false);
  const [uploads, setUploads] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    if (!assignmentId) return;
    api(`${base}/assignments/${assignmentId}`).then(data => {
      const version = data.versions.find(item => item.id === versionId);
      if (!data.can_edit || !version || version.status !== 'draft') throw new Error('This version cannot be edited.');
      setForm({ ...version, title: data.title, description: data.description ?? '', references: version.references.length ? version.references : initial.references, criteria: version.criteria.length ? version.criteria : initial.criteria });
    }).catch(err => setError(err.message)).finally(() => setLoading(false));
  }, [base, assignmentId, versionId]);
  useEffect(() => { onDirty(dirty || uploads > 0); return () => onDirty(false); }, [dirty, uploads, onDirty]);
  useEffect(() => {
    const prevent = event => { if (dirty || uploads) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', prevent); return () => window.removeEventListener('beforeunload', prevent);
  }, [dirty, uploads]);
  function change(field, value) { setForm(previous => ({ ...previous, [field]: value })); setDirty(true); setMessage(''); }
  function rowChange(field, index, key, value) { change(field, form[field].map((row, i) => i === index ? { ...row, [key]: value } : row)); }
  function uploadBusy(value) { setUploads(count => Math.max(0, count + (value ? 1 : -1))); }
  async function useInstructions(file) {
    setBusy(true); setError('');
    try { const result = await api(`${base}/files/${file.id}/text`); change('instructions', result.text); setMessage(result.truncated ? 'Imported the first 200,000 characters. Review the instructions before publishing.' : 'File text imported. Review it in Assignment Details before publishing.'); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function save() {
    let id = activeId, version = activeVersion, updated = form.updated_at;
    if (!form.title.trim()) throw new Error('Enter an assignment title.');
    if (!id) {
      const created = await post(`${base}/assignments`, { title: form.title, description: form.description });
      id = created.id; version = created.version.id; updated = created.version.updated_at;
      setActiveId(id); setActiveVersion(version); setForm(previous => ({ ...previous, updated_at: updated }));
    }
    const body = { ...form, updated_at: updated, file_ids: form.files.map(file => file.id),
      references: form.references.map(reference => ({ title: reference.title, answer_text: reference.answer_text ?? '', file_ids: reference.files.map(file => file.id) })) };
    const result = await api(`${base}/assignments/${id}/versions/${version}`, { method: 'PATCH', body: JSON.stringify(body) });
    setForm(previous => ({ ...previous, updated_at: result.updated_at })); setDirty(false); onDirty(false);
    return { id, version };
  }
  async function submit(event, publish = false) {
    event?.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      const saved = await save();
      if (publish) { await post(`${base}/assignments/${saved.id}/versions/${saved.version}/publish`); navigate(`/${base}/assignments/${saved.id}`, true); }
      else setMessage('Draft saved.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function next() {
    if (step === 0 && !activeId) { setBusy(true); setError(''); try { await save(); setStep(1); } catch (err) { setError(err.message); } finally { setBusy(false); } }
    else setStep(value => value + 1);
  }
  const points = form.criteria.reduce((sum, row) => sum + Number(row.max_points), 0);
  const files = [...form.files, ...form.references.flatMap(reference => reference.files)];
  const ready = files.every(file => file.processing_status === 'ready');
  const valid = form.instructions.trim() && form.criteria.length && Math.round(points * 100) === Math.round(Number(form.max_score) * 100) && form.references.some(reference => reference.answer_text?.trim() || reference.files.length) && ready;
  return <>
    <PageHeader title={assignmentId ? 'Edit Assignment' : 'Create Assignment'} description="Prepare instructions, answer keys, and a rubric before publishing."><Button secondary onClick={() => navigate(`/${base}/assignments`)}>Back to Assignments</Button></PageHeader>
    <Alert error={error} message={message} />
    {loading ? <p role="status">Loading draft…</p> : <>
      <ol className="mb-6 grid gap-2 sm:grid-cols-4">{['Assignment Details', 'Files & Answer Keys', 'Rubric', 'Review & Publish'].map((label, index) => <li key={label}><button disabled={busy || uploads > 0 || (!activeId && index > 0)} onClick={() => setStep(index)} className={`w-full rounded-xl border p-3 text-left text-sm ${step === index ? 'border-[#173b35] bg-[#e9f0e3] font-semibold' : 'border-slate-200 bg-white text-slate-500'} disabled:opacity-50`}><span className="mr-2">{index + 1}.</span>{label}</button></li>)}</ol>
      <form onSubmit={submit} className="rounded-2xl border border-[#dce2d8] bg-white p-6 sm:p-8">
        {step === 0 && <div className="space-y-5"><Field label="Title" required maxLength={200} value={form.title} onChange={e => change('title', e.target.value)} /><Field label="Description"><textarea rows={3} className={inputClass} value={form.description} onChange={e => change('description', e.target.value)} /></Field><Field label="Instructions"><textarea rows={7} className={inputClass} placeholder="Explain the task, or refer to the attached assignment files." value={form.instructions} onChange={e => change('instructions', e.target.value)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Maximum Score" type="number" min="0.01" max="99999999" step="0.01" required value={form.max_score} onChange={e => change('max_score', e.target.value)} /><Field label="Exemplar Threshold (%)" type="number" min="0" max="100" step="0.01" value={form.exemplar_threshold_percent} onChange={e => change('exemplar_threshold_percent', e.target.value)} /></div></div>}
        {step === 1 && <div className="space-y-8"><section><h2 className="mb-4 text-lg font-semibold">Assignment Files</h2><FileUpload base={base} assignmentId={activeId} purpose="assignment" files={form.files} onChange={files => change('files', files)} onBusyChange={uploadBusy} />{form.files.filter(file => file.processing_status === 'ready').map(file => <Button key={file.id} type="button" secondary disabled={busy} className="mt-3 mr-2" onClick={() => useInstructions(file)}>Use {file.original_filename} as Instructions</Button>)}</section><section><h2 className="text-lg font-semibold">Answer Keys</h2><p className="mt-2 text-sm text-slate-500">Provide text, files, or multiple acceptable solutions.</p>{form.references.map((reference, index) => <div key={index} className="mt-4 space-y-4 rounded-xl border border-slate-200 p-5"><Field label="Answer Key Title" required value={reference.title} onChange={e => rowChange('references', index, 'title', e.target.value)} /><Field label="Answer Text"><textarea rows={6} className={inputClass} value={reference.answer_text ?? ''} onChange={e => rowChange('references', index, 'answer_text', e.target.value)} /></Field><FileUpload base={base} assignmentId={activeId} purpose="reference" files={reference.files} onChange={files => rowChange('references', index, 'files', files)} onBusyChange={uploadBusy} /><Button type="button" secondary disabled={uploads > 0} onClick={() => change('references', form.references.filter((_, i) => i !== index))}>Remove Answer Key</Button></div>)}<Button type="button" secondary className="mt-4" onClick={() => change('references', [...form.references, { title: 'Answer key', answer_text: '', files: [] }])}>+ Add Answer Key</Button></section></div>}
        {step === 2 && <div><div className="mb-5 flex justify-between"><h2 className="text-lg font-semibold">Rubric Criteria</h2><span className={Math.round(points * 100) === Math.round(Number(form.max_score) * 100) ? 'text-green-700' : 'text-red-700'}>{points.toFixed(2)} / {form.max_score} points</span></div>{form.criteria.map((criterion, index) => <div key={index} className="mb-4 space-y-4 rounded-xl border border-slate-200 p-5"><div className="grid gap-4 sm:grid-cols-[1fr_140px]"><Field label="Criterion" required value={criterion.title} onChange={e => rowChange('criteria', index, 'title', e.target.value)} /><Field label="Points" type="number" min="0.01" step="0.01" required value={criterion.max_points} onChange={e => rowChange('criteria', index, 'max_points', e.target.value)} /></div><Field label="Description"><textarea rows={3} className={inputClass} value={criterion.description} onChange={e => rowChange('criteria', index, 'description', e.target.value)} /></Field><div className="flex gap-2"><Button type="button" secondary disabled={!index} onClick={() => { const rows = [...form.criteria]; [rows[index - 1], rows[index]] = [rows[index], rows[index - 1]]; change('criteria', rows); }}>Move Up</Button><Button type="button" secondary disabled={index === form.criteria.length - 1} onClick={() => { const rows = [...form.criteria]; [rows[index + 1], rows[index]] = [rows[index], rows[index + 1]]; change('criteria', rows); }}>Move Down</Button><Button type="button" secondary onClick={() => change('criteria', form.criteria.filter((_, i) => i !== index))}>Remove</Button></div></div>)}<Button type="button" secondary onClick={() => change('criteria', [...form.criteria, { title: '', description: '', max_points: 1 }])}>+ Add Criterion</Button></div>}
        {step === 3 && <div className="space-y-5"><h2 className="text-xl font-semibold">{form.title}</h2><p className="whitespace-pre-wrap text-sm leading-7">{form.instructions || 'Add instructions before publishing.'}</p><div className="rounded-xl bg-[#f5f7f2] p-5 text-sm leading-8"><p>Rubric: {form.criteria.length} criteria · {points.toFixed(2)} / {form.max_score} points</p><p>Answer keys: {form.references.length}</p><p>Attachments: {files.length} · {ready ? 'All files ready' : 'Some files are pending or failed'}</p></div>{!valid && <p className="text-sm text-red-700">Publication requires instructions, matching rubric totals, an answer key, and ready files.</p>}<p className="text-sm text-slate-500">Published versions cannot be edited. Future changes will use a new version.</p></div>}
        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-6"><Button type="submit" secondary disabled={busy || uploads > 0}>{busy ? 'Saving…' : 'Save Draft'}</Button><div className="flex gap-2">{step > 0 && <Button type="button" secondary disabled={busy || uploads > 0} onClick={() => setStep(value => value - 1)}>Previous</Button>}{step < 3 ? <Button type="button" disabled={busy || uploads > 0} onClick={next}>Next</Button> : <Button type="button" disabled={busy || uploads > 0 || !valid} onClick={() => submit(null, true)}>Publish Assignment</Button>}</div></div>
      </form>
    </>}
  </>;
}
