'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError, type RecordView } from '../../lib/api';
import { decodeRole, session } from '../../lib/session';

export default function RecordsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [records, setRecords] = useState<RecordView[]>([]);
  const [subjectName, setSubjectName] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (t: string) => {
    try {
      setRecords(await api.listRecords(t));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        session.clear();
        router.push('/login');
        return;
      }
      setError(err instanceof ApiError ? err.message : 'Failed to load records');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const t = session.get();
    if (!t) {
      router.push('/login');
      return;
    }
    setToken(t);
    setRole(decodeRole(t));
    load(t);
  }, [router, load]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.createRecord(token, subjectName, notes);
      setSubjectName('');
      setNotes('');
      await load(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create record');
    }
  }

  async function onDelete(id: string) {
    if (!token) return;
    try {
      await api.deleteRecord(token, id);
      await load(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete record');
    }
  }

  function signOut() {
    session.clear();
    router.push('/login');
  }

  const canDelete = role === 'admin';
  const canCreate = role === 'admin' || role === 'member';

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: '0 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ fontSize: 20 }}>Records</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {role && <span style={{ fontSize: 12, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5 }}>{role}</span>}
          <button onClick={signOut} style={{ fontSize: 13, background: 'none', border: '1px solid #ccc', borderRadius: 4, padding: '4px 10px', cursor: 'pointer' }}>
            Sign out
          </button>
        </div>
      </div>

      {canCreate && (
        <form onSubmit={onCreate} style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <input placeholder="Subject name" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} required style={{ flex: 1, padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4 }} />
          <input placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} required style={{ flex: 2, padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4 }} />
          <button type="submit" style={{ padding: '8px 14px', border: 'none', borderRadius: 4, background: '#111', color: 'white', cursor: 'pointer' }}>Add</button>
        </form>
      )}

      {error && <div style={{ color: '#b00020', fontSize: 13, marginBottom: 12 }}>{error}</div>}
      {loading && <p style={{ color: '#666' }}>Loading…</p>}
      {!loading && records.length === 0 && <p style={{ color: '#666' }}>No records yet.</p>}

      <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {records.map((r) => (
          <li key={r.id} style={{ background: 'white', border: '1px solid #e5e5e5', borderRadius: 6, padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <strong>{r.subject_name}</strong>
              <span style={{ fontSize: 11, textTransform: 'uppercase', color: '#666' }}>{r.status}</span>
            </div>
            <p style={{ fontSize: 13, color: '#333', margin: '6px 0' }}>{r.notes}</p>
            {r.ai_summary && <p style={{ fontSize: 12, color: '#0060df', fontStyle: 'italic' }}>Summary: {r.ai_summary}</p>}
            {canDelete && (
              <button onClick={() => onDelete(r.id)} style={{ fontSize: 12, color: '#b00020', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
