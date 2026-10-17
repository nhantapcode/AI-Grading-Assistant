import { useEffect, useState } from 'react';
import { api, post } from '../lib/api';
import SelectField from '../components/SelectField';
import { Alert, Badge, Button, Field, Modal, PageHeader, Pagination, tableClass } from '../components/ui';

export default function AccountsPage({ organization }) {
  const base = `organizations/${organization.id}`;
  const [tab, setTab] = useState('accounts');
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0 });
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({});
  const [link, setLink] = useState('');
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    const query = new URLSearchParams({ page, search, role, status });
    Promise.all([api(`${base}/members?${query}`), api(`${base}/invitations`)])
      .then(([people, invites]) => { if (active) { setData(people); setInvitations(invites); } })
      .catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, page, search, role, status, revision]);

  function open(type, member) {
    setError(''); setModal({ type, member }); setLink(''); setMessage('');
    setForm({ email: '', role: member?.role === 'admin' ? 'admin' : 'trainer', display_name_override: member?.display_name_override ?? '' });
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (modal.type === 'invite') {
        const result = await post(`${base}/invitations`, { email: form.email, role: form.role });
        setLink(result.link); setMessage('Invitation created. This link expires in 48 hours.');
      } else {
        const target = `${base}/members/${modal.member.id}`;
        const body = { updated_at: modal.member.updated_at, role: form.role, display_name_override: form.display_name_override };
        if (modal.type === 'edit') await api(target, { method: 'PATCH', body: JSON.stringify(body) });
        else await post(`${target}/${modal.type}`, body);
        setModal(null); setMessage('Account access updated.');
      }
      setRevision(value => value + 1);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function revokeInvite(invitation) {
    setBusy(true); setError('');
    try { await post(`${base}/invitations/${invitation.id}/revoke`); setRevision(value => value + 1); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader title={organization.role === 'owner' ? 'Accounts' : 'Members'} description="Manage your organization’s people and invitations."><Button onClick={() => open('invite')}>+ Invite Account</Button></PageHeader>
    {!modal && <Alert error={error} message={message} />}
    <div className="mb-5 flex gap-2"><Button secondary={tab !== 'accounts'} onClick={() => setTab('accounts')}>Accounts</Button><Button secondary={tab !== 'invitations'} onClick={() => setTab('invitations')}>Invitations</Button></div>
    {tab === 'accounts' && <div className="mb-5 grid gap-4 sm:grid-cols-3"><Field label="Search" placeholder="Name or email" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} /><SelectField label="Role" value={role} onChange={e => { setRole(e.target.value); setPage(1); }}><option value="">All roles</option><option value="owner">Owner</option><option value="admin">Admin</option><option value="trainer">Trainer</option></SelectField><SelectField label="Access Status" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option><option value="active">Active</option><option value="revoked">Revoked</option></SelectField></div>}
    {loading ? <p role="status" className="py-12 text-center text-slate-500">Loading accounts…</p> : <div className="overflow-x-auto rounded-2xl border border-[#dce2d8] bg-white">
      {tab === 'accounts' ? <table className={tableClass}><thead><tr>{['Name', 'Email', 'Role', 'Access Status', 'Joined', 'Actions'].map(text => <th key={text}>{text}</th>)}</tr></thead><tbody>{data.items.map(member => <tr key={member.id}><td className="font-medium">{member.display_name}</td><td>{member.email}</td><td><Badge>{member.role}</Badge></td><td><Badge>{member.status}</Badge></td><td>{new Date(member.created_at).toLocaleDateString('en-US')}</td><td><div className="flex gap-2">{organization.role === 'owner' && member.role !== 'owner' && <><Button secondary onClick={() => open('edit', member)}>Edit</Button><Button secondary={member.status === 'revoked'} danger={member.status === 'active'} onClick={() => open(member.status === 'active' ? 'revoke' : 'restore', member)}>{member.status === 'active' ? 'Remove Access' : 'Restore Access'}</Button></>}</div></td></tr>)}{!data.items.length && <tr><td colSpan={6} className="text-center text-slate-500">No accounts match your filters.</td></tr>}</tbody></table>
      : <table className={tableClass}><thead><tr>{['Email', 'Role', 'Invited By', 'Expires', 'Status', 'Actions'].map(text => <th key={text}>{text}</th>)}</tr></thead><tbody>{invitations.map(invitation => <tr key={invitation.id}><td>{invitation.email}</td><td><Badge>{invitation.role}</Badge></td><td>{invitation.invited_by_name}</td><td>{new Date(invitation.expires_at).toLocaleString('en-US')}</td><td><Badge>{invitation.status}</Badge></td><td>{invitation.status === 'pending' && <Button danger disabled={busy} onClick={() => revokeInvite(invitation)}>Revoke Invitation</Button>}</td></tr>)}{!invitations.length && <tr><td colSpan={6} className="text-center text-slate-500">No invitations yet.</td></tr>}</tbody></table>}
    </div>}
    {tab === 'accounts' && <Pagination page={page} total={data.total} onChange={setPage} />}
    {modal && <Modal title={{ invite: 'Invite Account', edit: 'Edit Account', revoke: 'Remove Access', restore: 'Restore Access' }[modal.type]} onClose={() => { if (!busy) setModal(null); }}>
      <Alert error={error} message={link ? message : ''} />
      {link ? <div className="space-y-4"><Field label="Invitation link" readOnly value={link} onFocus={e => e.target.select()} /><Button onClick={async () => { try { await navigator.clipboard.writeText(link); setMessage('Link copied.'); } catch { setError('Select the link and copy it manually.'); } }}>Copy Link</Button><p className="text-xs text-slate-500">Share this link with the invitee. It is shown only when created.</p></div> : <form onSubmit={submit} className="space-y-4">
        {modal.type === 'invite' ? <Field label="Email" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /> : <p className="text-sm leading-6"><strong>{modal.member.display_name}</strong><br />{modal.member.email}<br />{organization.name}</p>}
        {modal.type === 'revoke' ? <p className="text-sm text-slate-500">This account will immediately lose access to this organization. Assignment and grading history will be retained.</p> : <>
          {modal.type === 'edit' && <Field label="Name in this organization" maxLength={120} placeholder={modal.member.display_name} value={form.display_name_override} onChange={e => setForm({ ...form, display_name_override: e.target.value })} />}
          <SelectField label="Role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="trainer">Trainer</option>{organization.role === 'owner' && <option value="admin">Admin</option>}</SelectField>
        </>}
        <div className="flex justify-end gap-2"><Button type="button" secondary disabled={busy} onClick={() => setModal(null)}>Cancel</Button><Button type="submit" disabled={busy} danger={modal.type === 'revoke'}>{busy ? 'Saving…' : modal.type === 'invite' ? 'Create Invitation' : modal.type === 'revoke' ? 'Remove Access' : 'Save Changes'}</Button></div>
      </form>}
    </Modal>}
  </>;
}
