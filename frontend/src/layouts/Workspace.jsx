import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import SelectField from '../components/SelectField';
import { Alert, Button } from '../components/ui';
import AccountsPage from '../pages/AccountsPage';
import AssignmentsPage from '../pages/AssignmentsPage';
import AssignmentDetailPage from '../pages/AssignmentDetailPage';
import AssignmentEditorPage from '../pages/AssignmentEditorPage';
import SubmissionUploadPage from '../pages/SubmissionUploadPage';

function MenuIcon({ accounts }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="size-5 shrink-0">{accounts ? <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6M21 20v-2a6 6 0 0 0-3-5" /></> : <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V2h6v2M9 10h6M9 14h6M9 18h3" /></>}</svg>;
}

export default function Workspace({ user, signOut, busy, accountError }) {
  const [path, setPath] = useState(window.location.pathname);
  const [organizations, setOrganizations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const pathRef = useRef(path);
  dirtyRef.current = dirty; pathRef.current = path;
  const navigate = useCallback((target, force = false) => {
    if (!force && dirtyRef.current && !window.confirm('Leave this page and discard unsaved changes?')) return;
    setDirty(false); window.history.pushState(null, '', target); setPath(target);
  }, []);
  useEffect(() => {
    const update = () => {
      if (dirtyRef.current && !window.confirm('Leave this page and discard unsaved changes?')) { window.history.pushState(null, '', pathRef.current); return; }
      setDirty(false); setPath(window.location.pathname);
    };
    window.addEventListener('popstate', update); return () => window.removeEventListener('popstate', update);
  }, []);
  useEffect(() => {
    let active = true;
    api('organizations').then(items => {
      if (!active) return;
      setOrganizations(items);
      if (!path.startsWith('/organizations/') && path !== '/account' && items.length) {
        const first = items[0]; navigate(`/organizations/${first.id}/${first.role === 'owner' ? 'accounts' : first.role === 'admin' ? 'members' : 'assignments'}`, true);
      }
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, navigate]);
  const pieces = path.split('/').filter(Boolean);
  const organization = organizations.find(item => item.id === pieces[1]) ?? (!path.startsWith('/organizations/') ? organizations[0] : null);
  const screen = pieces[2];
  const root = organization ? `/organizations/${organization.id}` : '';
  const assignmentId = pieces[3];
  let page;
  if (path === '/account' || (!organization && !path.startsWith('/organizations/'))) {
    page = <div className="max-w-xl rounded-2xl border border-[#dce2d8] bg-white p-8"><h1 className="text-3xl font-semibold">My Account</h1><p className="mt-5 font-medium">{user.display_name}</p><p className="mt-2 break-all text-slate-500">{user.email}</p>{!organizations.length && <p className="mt-5 text-sm text-slate-500">You have no active organization memberships. Contact your administrator for an invitation.</p>}</div>;
  } else if (organization) {
    const props = { organization, user, navigate };
    if (screen === 'accounts' || screen === 'members') page = ['owner', 'admin'].includes(organization.role) ? <AccountsPage {...props} /> : <Alert error="Only owners and admins can manage members." />;
    else if (screen === 'assignments' && !['admin', 'trainer'].includes(organization.role)) page = <Alert error="Assignment pages are available to admins and trainers. Use Accounts to manage your organization." />;
    else if (screen === 'assignments' && assignmentId === 'new') page = <AssignmentEditorPage {...props} onDirty={setDirty} />;
    else if (screen === 'assignments' && pieces[4] === 'versions' && pieces[6] === 'edit') page = <AssignmentEditorPage {...props} assignmentId={assignmentId} versionId={pieces[5]} onDirty={setDirty} />;
    else if (screen === 'assignments' && pieces[4] === 'submissions' && pieces[5] === 'upload') page = <SubmissionUploadPage {...props} assignmentId={assignmentId} onDirty={setDirty} />;
    else if (screen === 'assignments' && assignmentId) page = <AssignmentDetailPage {...props} assignmentId={assignmentId} />;
    else if (screen === 'assignments') page = <AssignmentsPage {...props} />;
    else page = <Alert error="Page not found. Choose a page from the navigation." />;
  } else page = <Alert error="You do not have access to this organization. Choose another organization or contact your administrator." />;

  return <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
    <aside className="flex flex-col border-b border-[#dce2d8] bg-[#f0f3eb] p-6 lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
      <div className="mb-8 flex items-center gap-3"><span aria-hidden="true" className="grid size-10 place-items-center rounded-xl bg-[#173b35] text-xl text-white">✦</span><span className="text-sm font-semibold leading-5">AI Grading<br />Assistant</span></div>
      {organizations.length > 0 && <SelectField label="Organization" value={organization?.id ?? ''} onChange={e => { const selected = organizations.find(item => item.id === e.target.value); navigate(`/organizations/${selected.id}/${selected.role === 'owner' ? 'accounts' : selected.role === 'admin' ? 'members' : 'assignments'}`); }}><option value="" disabled>Choose organization</option>{organizations.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>}
      <nav aria-label="Workspace navigation" className="mt-6 flex flex-wrap gap-2 lg:flex-col">{organization && <>
        {['owner', 'admin'].includes(organization.role) && <button aria-current={['accounts', 'members'].includes(screen) ? 'page' : undefined} onClick={() => navigate(`${root}/${organization.role === 'owner' ? 'accounts' : 'members'}`)} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm ${['accounts', 'members'].includes(screen) ? 'bg-[#173b35] text-white' : 'hover:bg-white'}`}><MenuIcon accounts />{organization.role === 'owner' ? 'Accounts' : 'Members'}</button>}
        {['admin', 'trainer'].includes(organization.role) && <button aria-current={screen === 'assignments' ? 'page' : undefined} onClick={() => navigate(`${root}/assignments`)} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm ${screen === 'assignments' ? 'bg-[#173b35] text-white' : 'hover:bg-white'}`}><MenuIcon />Assignments</button>}
      </>}<button aria-current={path === '/account' ? 'page' : undefined} onClick={() => navigate('/account')} className={`rounded-xl px-4 py-3 text-left text-sm ${path === '/account' ? 'bg-[#173b35] text-white' : 'hover:bg-white'}`}>My Account</button></nav>
      <div className="mt-6 border-t border-[#dce2d8] pt-5 lg:mt-auto"><p className="truncate text-sm font-semibold">{user.display_name}</p><p className="mt-1 truncate text-xs text-slate-500">{user.email}</p><p className="mt-2 text-xs capitalize text-slate-500">{organization?.role}</p><Button secondary disabled={busy} className="mt-4 w-full" onClick={() => { if (!dirty || window.confirm('Sign out and discard unsaved changes?')) signOut(); }}>{busy ? 'Signing out…' : 'Sign out'}</Button></div>
    </aside>
    <main className="min-w-0 p-5 sm:p-8 lg:p-10"><div className="mx-auto max-w-6xl"><Alert error={accountError || error} />{loading ? <p role="status">Loading workspace…</p> : <div key={path}>{page}</div>}</div></main>
  </div>;
}
