import { describe, expect, it } from 'vitest';
import { decodeRole } from '../lib/session';

function fakeJwt(payload: object): string {
  const b64 = (obj: object) => Buffer.from(JSON.stringify(obj)).toString('base64');
  return `${b64({ alg: 'none' })}.${b64(payload)}.signature`;
}

describe('decodeRole', () => {
  it('reads the role claim out of a JWT payload', () => {
    expect(decodeRole(fakeJwt({ role: 'admin' }))).toBe('admin');
  });

  it('returns null for a token with no role claim', () => {
    expect(decodeRole(fakeJwt({ sub: 'user-1' }))).toBeNull();
  });

  it('returns null rather than throwing on a malformed token', () => {
    expect(decodeRole('not-a-jwt')).toBeNull();
  });
});
