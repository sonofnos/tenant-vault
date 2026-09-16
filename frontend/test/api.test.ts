import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../lib/api';

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  function jsonResponse(status: number, body: unknown) {
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  }

  it('sends the bearer token on authenticated calls', async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(200, []));
    await api.listRecords('tok-123');
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
  });

  it('does not send an Authorization header for login', async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(200, { access_token: 'x', token_type: 'bearer' }));
    await api.login('acme', 'a@example.com', 'pw');
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('surfaces the API error detail message and status on a non-2xx response', async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(422, { detail: 'organization slug already taken' }));
    await expect(api.signup('Acme', 'acme', 'a@example.com', 'password123')).rejects.toMatchObject({
      status: 422,
      message: 'organization slug already taken',
    });
  });

  it('rejects with ApiError, not a generic Error, on failure', async () => {
    fetchMock.mockReturnValueOnce(jsonResponse(401, { detail: 'invalid credentials' }));
    await expect(api.login('acme', 'a@example.com', 'wrong')).rejects.toBeInstanceOf(ApiError);
  });

  it('treats a 204 response as no content rather than trying to parse JSON', async () => {
    fetchMock.mockReturnValueOnce(Promise.resolve(new Response(null, { status: 204 })));
    await expect(api.deleteRecord('tok', 'id-1')).resolves.toBeUndefined();
  });
});
