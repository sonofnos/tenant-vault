'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '../../lib/api';
import { session } from '../../lib/session';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [orgName, setOrgName] = useState('');
  const [orgSlug, setOrgSlug] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'signup') {
        await api.signup(orgName, orgSlug, email, password);
      }
      const { access_token } = await api.login(orgSlug, email, password);
      session.set(access_token);
      router.push('/records');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 380, margin: '80px auto', padding: 24, background: 'white', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>tenant-vault</h1>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 20 }}>{mode === 'login' ? 'Sign in to your organization' : 'Create a new organization'}</p>
      <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {mode === 'signup' && (
          <input placeholder="Organization name" value={orgName} onChange={(e) => setOrgName(e.target.value)} required style={inputStyle} />
        )}
        <input placeholder="Organization slug (e.g. acme)" value={orgSlug} onChange={(e) => setOrgSlug(e.target.value)} required style={inputStyle} />
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required style={inputStyle} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} style={inputStyle} />
        {error && <div style={{ color: '#b00020', fontSize: 13 }}>{error}</div>}
        <button type="submit" disabled={busy} style={buttonStyle}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create organization'}
        </button>
      </form>
      <button onClick={() => setMode(mode === 'login' ? 'signup' : 'login')} style={{ marginTop: 14, background: 'none', border: 'none', color: '#0060df', cursor: 'pointer', fontSize: 13 }}>
        {mode === 'login' ? 'Need an organization? Create one' : 'Already have an account? Sign in'}
      </button>
    </main>
  );
}

const inputStyle: React.CSSProperties = { padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 };
const buttonStyle: React.CSSProperties = { padding: '9px 10px', border: 'none', borderRadius: 4, background: '#111', color: 'white', fontSize: 14, cursor: 'pointer' };
