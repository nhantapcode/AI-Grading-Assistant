import { useEffect, useState } from 'react';
import { api, post } from '../lib/api';
import { FileList } from '../components/FileUpload';
import SelectField from '../components/SelectField';
import { Alert, Badge, Button, PageHeader, Pagination, tableClass } from '../components/ui';

export default function AssignmentDetailPage({ organization, user, assignmentId, navigate }) {
  const base = `organizations/${organization.id}`;
  const root = `/${base}/assignments/${assignmentId}`;
  const [data, setData] = useState(null);
  const [versionId, setVersionId] = useState('');
  const [tab, setTab] = useState('Overview');
  const [submissions, setSubmissions] = useState({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const version = data?.versions.find(item => item.id === versionId);
  useEffect(() => {
    api(`${base}/assignments/${assignmentId}`).then(result => { setData(result); setVersionId(result.versions[0]?.id ?? ''); }).catch(err => setError(err.message));
  }, [base, assignmentId]);
  useEffect(() => {
    if (tab !== 'Submissions') return;
    api(`${base}/assignments/${assignmentId}/submissions?page=${page}`).then(setSubmissions).catch(err => setError(err.message));
  }, [base, assignmentId, tab, page]);
  async function newVersion() {
    setBusy(true); setError('');
    try { const result = await post(`${base}/assignments/${assignmentId}/versions`); navigate(`${root}/versions/${result.id}/edit`); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  const draft = data?.versions.find(item => item.status === 'draft');
  return <>
    <Alert error={error} />
    {!data ? !error && <p role="status">Loading assignment…</p> : <>
      <PageHeader title={data.title} description={data.description || 'Assignment details and version history.'}><Button secondary onClick={() => navigate(`/${base}/assignments`)}>Back</Button>{data.can_edit && <>{draft ? <Button onClick={() => navigate(`${root}/versions/${draft.id}/edit`)}>Edit Draft</Button> : <Button disabled={busy} onClick={newVersion}>New Version</Button>}{data.versions.some(item => item.status === 'published') && <Button secondary onClick={() => navigate(`${root}/submissions/upload`)}>Upload Submissions</Button>}</>}</PageHeader>
      <div className="mb-5 max-w-sm"><SelectField label="Version" value={versionId} onChange={e => setVersionId(e.target.value)}>{data.versions.map(item => <option key={item.id} value={item.id}>Version {item.version_number} · {item.status}</option>)}</SelectField></div>
      <div className="mb-6 flex flex-wrap gap-2">{['Overview', 'Files', 'Rubric', 'Answer Keys', ...(data.created_by === user?.id || ['owner', 'admin'].includes(organization.role) ? ['Submissions'] : [])].map(name => <Button key={name} secondary={tab !== name} onClick={() => setTab(name)}>{name}</Button>)}</div>
      <div className="rounded-2xl border border-[#dce2d8] bg-white p-6">
        {tab === 'Overview' && version && <><Badge>{version.status}</Badge><p className="mt-4 text-sm text-slate-500">Maximum score: {version.max_score} · Exemplar threshold: {version.exemplar_threshold_percent}%</p><h2 className="mt-6 font-semibold">Instructions</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-7">{version.instructions || 'No instructions yet.'}</p></>}
        {tab === 'Files' && <><FileList files={version?.files ?? []} base={base} />{!version?.files.length && <p className="text-sm text-slate-500">No assignment files attached.</p>}</>}
        {tab === 'Rubric' && <div className="space-y-4">{version?.criteria.map(criterion => <div key={criterion.id} className="rounded-xl bg-[#f5f7f2] p-4"><div className="flex justify-between gap-4"><h3 className="font-medium">{criterion.title}</h3><span>{criterion.max_points} points</span></div><p className="mt-2 text-sm text-slate-500">{criterion.description}</p></div>)}{!version?.criteria.length && <p className="text-sm text-slate-500">No rubric criteria yet.</p>}</div>}
        {tab === 'Answer Keys' && <div className="space-y-6">{version?.references.map(reference => <section key={reference.id}><h3 className="font-semibold">{reference.title}</h3><p className="my-4 whitespace-pre-wrap text-sm leading-7">{reference.answer_text}</p><FileList files={reference.files} base={base} /></section>)}{!version?.references.length && <p className="text-sm text-slate-500">No answer keys yet.</p>}</div>}
        {tab === 'Submissions' && <><div className="overflow-x-auto"><table className={tableClass}><thead><tr>{['Student', 'Version', 'Attempt', 'Status', 'Score', 'Files'].map(title => <th key={title}>{title}</th>)}</tr></thead><tbody>{submissions.items.map(submission => <tr key={submission.id}><td>{submission.student}<br /><span className="text-xs text-slate-500">{submission.external_student_id}</span></td><td>v{submission.version_number}</td><td>{submission.attempt_number}</td><td><Badge>{submission.status === 'ready' ? 'Ready for grading' : submission.status}</Badge></td><td>{submission.total_score ?? '—'}</td><td>{submission.files.map(file => <a key={file.id} href={`/api/${base}/files/${file.id}/download`} className="block py-1 underline">{file.original_filename}</a>)}</td></tr>)}{!submissions.items.length && <tr><td colSpan={6} className="text-center text-slate-500">No submissions yet.</td></tr>}</tbody></table></div><Pagination page={page} total={submissions.total} onChange={setPage} /></>}
      </div>
    </>}
  </>;
}
