export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface RecordView {
  id: string;
  subject_name: string;
  notes: string;
  status: 'open' | 'reviewed' | 'closed';
  ai_summary: string | null;
  created_at: string;
  updated_at: string;
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : res.statusText;
    throw new ApiError(res.status, message);
  }
  return data as T;
}

export const api = {
  login: (organizationSlug: string, email: string, password: string) =>
    request<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ organization_slug: organizationSlug, email, password }) }),
  signup: (organizationName: string, organizationSlug: string, email: string, password: string) =>
    request<{ org_id: string; user_id: string }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ organization_name: organizationName, organization_slug: organizationSlug, email, password }),
    }),
  listRecords: (token: string) => request<RecordView[]>('/records', {}, token),
  createRecord: (token: string, subjectName: string, notes: string) =>
    request<RecordView>('/records', { method: 'POST', body: JSON.stringify({ subject_name: subjectName, notes }) }, token),
  updateStatus: (token: string, id: string, status: string) =>
    request<RecordView>(`/records/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }, token),
  deleteRecord: (token: string, id: string) => request<void>(`/records/${id}`, { method: 'DELETE' }, token),
};
