import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import SelectField from '../components/SelectField';
import { Alert, Badge, Button, Field, PageHeader, Pagination, tableClass } from '../components/ui';

export default function AssignmentsPage({ organization, user, navigate }) {
  const root = `/organizations/${organization.id}`;
  const isTrainer = organization.role === 'trainer';
  const [search, setSearch] = useState('');
  const [author, setAuthor] = useState('');
  const [authors, setAuthors] = useState([]);
  const [status, setStatus] = useState('');
  const [since, setSince] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0 });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => { if (!isTrainer) api(`organizations/${organization.id}/assignment-authors`).then(setAuthors).catch(err => setError(err.message)); }, [organization.id, isTrainer]);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    const query = new URLSearchParams({ search, status, page });
    // trainer luôn chỉ thấy bài của mình; admin lọc theo author nếu chọn
    if (isTrainer) query.set('author', user.id);
    else if (author) query.set('author', author);
    if (since) query.set('updated_since', new Date(since).toISOString());
    api(`organizations/${organization.id}/assignments?${query}`).then(result => { if (active) setData(result); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [organization.id, user.id, isTrainer, search, author, status, since, page]);
  return <>
    <PageHeader title="Assignments" description={isTrainer ? 'Manage your assignments and prepare new assessments.' : "Explore your organization's assignments."}>
      <Button onClick={() => navigate(`${root}/assignments/new`)}>+ Create Assignment</Button>
    </PageHeader>
    <Alert error={error} />
    <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Field label="Search" placeholder="Assignment title" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
      {!isTrainer && <SelectField label="Author" value={author} onChange={e => { setAuthor(e.target.value); setPage(1); }}><option value="">All authors</option>{authors.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</SelectField>}
      <SelectField label="Status" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option><option value="draft">Draft</option><option value="active">Active</option><option value="archived">Archived</option></SelectField>
      <Field label="Updated since" type="date" value={since} onChange={e => { setSince(e.target.value); setPage(1); }} />
    </div>
    {loading ? <p role="status" className="py-12 text-center text-slate-500">Loading assignments…</p> : <div className="overflow-x-auto rounded-2xl border border-[#dce2d8] bg-white"><table className={tableClass}><thead><tr>{['Title', ...(isTrainer ? [] : ['Author']), 'Published Version', 'Status', 'Updated', 'Actions'].map(title => <th key={title}>{title}</th>)}</tr></thead><tbody>{data.items.map(assignment => <tr key={assignment.id}><td className="font-medium">{assignment.title}</td>{!isTrainer && <td>{assignment.author}</td>}<td>{assignment.published_version ? `v${assignment.published_version}` : '—'}</td><td><Badge>{assignment.status}</Badge></td><td>{new Date(assignment.updated_at).toLocaleDateString('en-US')}</td><td><Button secondary onClick={() => navigate(`${root}/assignments/${assignment.id}`)}>View Details</Button></td></tr>)}{!data.items.length && <tr><td colSpan={isTrainer ? 5 : 6} className="text-center text-slate-500">No assignments found. Create your first assignment to get started.</td></tr>}</tbody></table></div>}
    <Pagination page={page} total={data.total} onChange={setPage} />
  </>;
}
