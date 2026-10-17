import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

import { api as request } from './lib/api';
import Workspace from './layouts/Workspace';
import AcceptInvitation from './components/AcceptInvitation';

const api = (path, options) => request(`auth/${path}`, options);

function App() {
  const [user, setUser] = useState(null);
  const [inviteToken, setInviteToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('invite'));
  useEffect(() => {
    const update = () => setInviteToken(new URLSearchParams(window.location.hash.slice(1)).get('invite'));
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  function finishInvitation(invitedEmail) {
    window.history.replaceState(null, '', window.location.pathname);
    setInviteToken(null);
    if (invitedEmail) { setEmail(invitedEmail); setNotice(user ? 'You have successfully joined the organization.' : 'Your account is ready. You can now sign in.'); }
  }
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    api('me').then(setUser).catch(err => { if (err.status !== 401) setError(err.message); }).finally(() => setChecking(false));
  }, []);
  useEffect(() => { document.title = `${user ? 'Your account' : 'Sign in'} · AI Grading Assistant`; }, [user]);

  async function signIn(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try { setUser(await api('login', { method: 'POST', body: JSON.stringify({ email, password }) })); setPassword(''); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function signOut() {
    setBusy(true); setError('');
    try { await api('logout', { method: 'POST' }); if (!inviteToken) window.history.replaceState(null, '', '/'); setUser(null); setNotice('You have been signed out.'); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  if (user && !inviteToken && !checking) return <Workspace user={user} signOut={signOut} busy={busy} accountError={error} />;

  return <main className="min-h-screen p-5 sm:p-8 lg:p-12 flex flex-col">
    <header className="flex items-center gap-3"><span aria-hidden="true" className="grid size-10 place-items-center rounded-xl bg-[#173b35] text-xl text-white">✦</span><span className="font-semibold tracking-tight">AI Grading Assistant</span></header>
    <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 py-12 lg:grid-cols-2 lg:gap-24">
      <section className="relative overflow-hidden rounded-[2rem] bg-[#173b35] p-8 text-white sm:p-12 lg:min-h-[580px] flex flex-col justify-between">
        <div className="absolute -right-24 -top-24 size-80 rounded-full border border-white/10" aria-hidden="true" />
        <div className="absolute -right-12 -top-12 size-56 rounded-full border border-white/10" aria-hidden="true" />
        <div className="relative"><p className="text-xs uppercase tracking-[.22em] text-[#c8e4b7]">A little support. A lot of potential.</p><h1 className="mt-8 text-4xl font-medium leading-tight tracking-tight sm:text-5xl">More time for<br />the moments<br /><span className="text-[#c8e4b7]">that teach.</span></h1><p className="mt-6 max-w-sm text-base leading-7 text-white/65">Your space for thoughtful assessment, clear feedback, and student progress.</p></div>
        <div className="relative mt-12 rounded-2xl border border-white/15 bg-white/5 p-6"><span aria-hidden="true" className="text-2xl text-[#c8e4b7]">✧</span><p className="mt-4 text-lg">Built to support your judgment.</p><p className="mt-2 text-sm leading-6 text-white/60">You bring the expertise. We help with the groundwork.</p></div>
      </section>
      <section className="mx-auto w-full max-w-md" aria-label={user ? 'Account' : 'Sign in'}>
        {checking ? <p role="status" className="text-center text-sm text-slate-500">Checking your session…</p> : inviteToken ? <AcceptInvitation token={inviteToken} user={user} onLogin={setUser} onSignOut={signOut} onDone={finishInvitation} signingOut={busy} accountError={error} /> : <>
          <p className="text-xs font-semibold uppercase tracking-[.2em] text-[#6c8579]">{user ? 'Your workspace' : 'Welcome back'}</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{user ? `Hello, ${user.display_name}.` : 'Sign in to your account'}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-500">{user ? 'You’re signed in to AI Grading Assistant.' : 'Enter your details to access your workspace.'}</p>
          {error && <div role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
          {notice && <div role="status" className="mt-6 rounded-xl bg-[#e6efdf] p-4 text-sm">{notice}</div>}
          {user ? <div className="mt-8"><div className="rounded-2xl border border-[#dce2d8] bg-white p-6"><p className="text-xs uppercase tracking-wider text-slate-500">Signed in as</p><p className="mt-2 break-all font-medium">{user.email}</p><p className="mt-4 text-sm text-slate-500">Manage members and invitations in your organization.</p></div><button onClick={signOut} disabled={busy} className="mt-6 w-full rounded-xl bg-[#173b35] px-4 py-3.5 font-medium text-white transition hover:bg-[#265248] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#173b35] disabled:opacity-60">{busy ? 'Signing out…' : 'Sign out'}</button></div>
          : <form onSubmit={signIn} className="mt-8 space-y-5">
            <div><label htmlFor="email" className="mb-2 block text-sm font-medium">Email address</label><input id="email" type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" className="w-full rounded-xl border border-[#d5ddd3] bg-white px-4 py-3.5 text-sm outline-none focus:border-[#173b35] focus:ring-2 focus:ring-[#173b35]/10" /></div>
            <div><label htmlFor="password" className="mb-2 block text-sm font-medium">Password</label><div className="relative"><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required maxLength={1024} value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password" className="w-full rounded-xl border border-[#d5ddd3] bg-white py-3.5 pl-4 pr-18 text-sm outline-none focus:border-[#173b35] focus:ring-2 focus:ring-[#173b35]/10" /><button type="button" aria-controls="password" aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)} className="absolute inset-y-0 right-3 px-2 text-xs font-medium text-slate-500 focus-visible:outline-2">{showPassword ? 'Hide' : 'Show'}</button></div></div>
            <button disabled={busy} className="w-full rounded-xl bg-[#173b35] px-4 py-3.5 font-medium text-white transition hover:bg-[#265248] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#173b35] disabled:opacity-60">{busy ? 'Signing in…' : 'Sign in →'}</button>
            <p className="text-center text-xs leading-6 text-slate-500">Need access? Contact your organization’s administrator.</p>
          </form>}
        </>}
      </section>
    </div>
    <footer className="text-center text-xs text-slate-500">Thoughtful feedback starts here.</footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
