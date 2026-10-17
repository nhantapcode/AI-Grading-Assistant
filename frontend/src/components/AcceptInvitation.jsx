import { useEffect, useState } from 'react';
import { post } from '../lib/api';

const input = 'mt-2 w-full rounded-xl border border-slate-300 bg-white p-3 text-sm';
const button = 'w-full rounded-xl bg-[#173b35] p-3 text-white disabled:opacity-50';

export default function AcceptInvitation({ token, user, onLogin, onSignOut, onDone, signingOut, accountError }) {
  const [invitation, setInvitation] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setInvitation(null);
    post('invitations/resolve', { token }).then(value => { if (active) setInvitation(value); })
      .catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token]);

  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (invitation.account_exists && !user) {
        onLogin(await post('auth/login', { email: invitation.email, password }));
        setPassword('');
      } else {
        if (!invitation.account_exists && password !== confirm) throw new Error('Passwords do not match');
        await post('invitations/accept', { token, ...(!invitation.account_exists ? { display_name: name, password } : {}) });
        onDone(invitation.email);
      }
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div>
    <p className="text-xs uppercase tracking-widest text-slate-500">Organization invitation</p>
    <h2 className="mt-3 text-3xl font-semibold">{invitation?.organization_name ?? 'Join an organization'}</h2>
    {loading && <p role="status" className="mt-4">Checking your invitation…</p>}
    {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p>}
    {accountError && <p role="alert" className="mt-4 text-sm text-red-700">{accountError}</p>}
    {!loading && !invitation && <p className="mt-4 text-sm text-slate-500">Contact your administrator for a new invitation.</p>}
    {invitation && <>
      <p className="mt-4 break-all text-sm">{invitation.email} · Role: {invitation.role}</p>
      <p className="mt-2 text-xs text-slate-500">Expires: {new Date(invitation.expires_at).toLocaleString('en-US')}</p>
      {user && user.email !== invitation.email ? <div className="mt-6 space-y-4"><p className="text-sm">You are signed in with a different email. Sign out to continue.</p><button disabled={signingOut} onClick={onSignOut} className={button}>{signingOut ? 'Signing out…' : 'Sign out'}</button></div> : <form onSubmit={submit} className="mt-6 space-y-4">
        {!invitation.account_exists && <label className="block text-sm">Full name<input className={input} autoComplete="name" required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>}
        {(!invitation.account_exists || !user) && <label className="block text-sm">{invitation.account_exists ? 'Your account password' : 'Password (at least 12 characters)'}<input className={input} type="password" autoComplete={invitation.account_exists ? 'current-password' : 'new-password'} required minLength={invitation.account_exists ? 1 : 12} maxLength={1024} value={password} onChange={e => setPassword(e.target.value)} /></label>}
        {!invitation.account_exists && <label className="block text-sm">Confirm password<input className={input} type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={confirm} onChange={e => setConfirm(e.target.value)} /></label>}
        <button disabled={busy} className={button}>{busy ? 'Working…' : invitation.account_exists && !user ? 'Sign in to continue' : invitation.account_exists ? 'Accept invitation' : 'Create account and join'}</button>
      </form>}
    </>}
    <button onClick={() => onDone()} className="mt-5 text-sm underline">Back to your account</button>
  </div>;
}
