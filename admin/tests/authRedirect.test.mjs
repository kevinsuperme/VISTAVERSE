import assert from 'node:assert/strict';
import test from 'node:test';
import { buildLoginRedirect, safeNextPath } from '../src/lib/authRedirect.ts';

test('admin session expiry preserves a safe route', () => {
  assert.equal(safeNextPath('/users?page=2#row-3'), '/users?page=2#row-3');
  assert.equal(safeNextPath('https://attacker.invalid/'), '/');
  assert.equal(buildLoginRedirect('/users?page=2#row-3'), '/login?next=%2Fusers%3Fpage%3D2%23row-3');
});
