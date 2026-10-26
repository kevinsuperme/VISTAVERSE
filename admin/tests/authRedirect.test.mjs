import assert from 'node:assert/strict';
import test from 'node:test';
import { buildLoginRedirect, safeNextPath, sessionLoginRedirect } from '../src/lib/authRedirect.ts';

test('admin session expiry preserves a safe route', () => {
  assert.equal(safeNextPath('/users?page=2#row-3'), '/users?page=2#row-3');
  assert.equal(safeNextPath('https://attacker.invalid/'), '/');
  assert.equal(buildLoginRedirect('/users?page=2#row-3'), '/login?next=%2Fusers%3Fpage%3D2%23row-3');
});

test('session expiry retains production basename once and preserves deep links', () => {
  assert.equal(sessionLoginRedirect('/admin/orders', '?order=42&page=3', '#detail', '/admin/'), '/admin/login?next=%2Forders%3Forder%3D42%26page%3D3%23detail');
  assert.equal(sessionLoginRedirect('/works', '?work=8', '', '/'), '/login?next=%2Fworks%3Fwork%3D8');
  assert.equal(sessionLoginRedirect('/admin/login', '?next=%2Fusers', '', '/admin/'), null);
  assert.equal(sessionLoginRedirect('/login', '', '', '/'), null);
});
