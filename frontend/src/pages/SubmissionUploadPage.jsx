import { useEffect, useRef, useState } from 'react';
import { api, post } from '../lib/api';
import FileUpload from '../components/FileUpload';
import SelectField from '../components/SelectField';
import { Alert, Button, Field, Modal, PageHeader } from '../components/ui';

export default function SubmissionUploadPage({ organization, assignmentId, navigate, onDirty }) {
  const base = `organizations/${organization.id}`;
  const [assignment, setAssignment] = useState(null);
  const [version, setVersion] = useState('');
  const [students, setStudents] = useState({ items: [], total: 0 });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [student, setStudent] = useState('');
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ external_student_id: '', display_name: '', email: '' });
  const requestKey = useRef(crypto.randomUUID());
  const createdSubmission = useRef(null);
  const fingerprint = `${student}:${version}:${files.map(file => file.id).join(',')}`;
  useEffect(() => { requestKey.current = crypto.randomUUID(); createdSubmission.current = null; }, [fingerprint]);
  useEffect(() => {
    api(`${base}/assignments/${assignmentId}`).then(data => {
      if (!data.can_edit) throw new Error('You cannot upload submissions for this assignment.');
      setAssignment(data); setVersion(data.versions.find(item => item.status === 'published')?.id ?? '');
    }).catch(err => setError(err.message));
  }, [base, assignmentId]);
  useEffect(() => {
    let active = true;
    api(`${base}/students?${new URLSearchParams({ search, page, limit: 100 })}`).then(result => { if (active) setStudents(result); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [base, search, page]);
  useEffect(() => { onDirty(files.length > 0 || uploading); return () => onDirty(false); }, [files.length, uploading, onDirty]);
  useEffect(() => {
    const prevent = event => { if (files.length || uploading) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', prevent); return () => window.removeEventListener('beforeunload', prevent);
  }, [files.length, uploading]);
  async function createStudent(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { const result = await post(`${base}/students`, { ...form, email: form.email || null }); setStudents(previous => ({ ...previous, items: [result, ...previous.items], total: previous.total + 1 })); setStudent(result.id); setModal(false); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (!createdSubmission.current) createdSubmission.current = await post(`${base}/assignments/${assignmentId}/submissions`, { assignment_version_id: version, student_id: student, file_ids: files.map(file => file.id), idempotency_key: requestKey.current });
      await post(`${base}/submissions/${createdSubmission.current.id}/finalize`);
      onDirty(false); navigate(`/${base}/assignments/${assignmentId}`, true);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <>
    <PageHeader title="Upload Submissions" description={assignment ? `${assignment.title} · Submit work on behalf of one student.` : 'Choose a student and upload their work.'}><Button secondary onClick={() => navigate(`/${base}/assignments/${assignmentId}`)}>Back</Button></PageHeader>
    {!modal && <Alert error={error} />}
    {!assignment ? !error && <p role="status">Loading assignment…</p> : <form onSubmit={submit} className="max-w-3xl space-y-6 rounded-2xl border border-[#dce2d8] bg-white p-6 sm:p-8">
      <SelectField label="Published Version" required value={version} onChange={e => setVersion(e.target.value)}><option value="">Choose a version</option>{assignment.versions.filter(item => item.status === 'published').map(item => <option key={item.id} value={item.id}>Version {item.version_number}</option>)}</SelectField>
      <div className="space-y-4"><Field label="Find Student" placeholder="Name or student ID" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} /><SelectField label="Student" required value={student} onChange={e => setStudent(e.target.value)}><option value="">Choose a student</option>{students.items.map(item => <option key={item.id} value={item.id}>{item.display_name} ({item.external_student_id})</option>)}</SelectField><div className="flex flex-wrap gap-2"><Button type="button" secondary onClick={() => { setModal(true); setError(''); }}>+ New Student</Button>{students.total > 100 && <><Button type="button" secondary disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous Students</Button><Button type="button" secondary disabled={page * 100 >= students.total} onClick={() => setPage(value => value + 1)}>Next Students</Button></>}</div></div>
      <FileUpload base={base} assignmentId={assignmentId} purpose="submission" files={files} onChange={setFiles} onBusyChange={setUploading} />
      <p className="text-sm leading-6 text-slate-500">A ZIP represents one student’s work. New submissions create a new attempt and retain previous attempts. Completed uploads are ready for grading; AI grading is not enabled yet.</p>
      <Button type="submit" disabled={busy || uploading || !version || !student || !files.length || files.some(file => file.processing_status !== 'ready')}>{busy ? 'Submitting…' : 'Submit'}</Button>
    </form>}
    {modal && <Modal title="Create Student" onClose={() => { if (!busy) setModal(false); }}><Alert error={error} /><form onSubmit={createStudent} className="space-y-4"><Field label="Student ID" required maxLength={120} value={form.external_student_id} onChange={e => setForm({ ...form, external_student_id: e.target.value })} /><Field label="Full Name" required maxLength={120} value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /><Field label="Email (optional)" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Create Student'}</Button></form></Modal>}
  </>;
}
