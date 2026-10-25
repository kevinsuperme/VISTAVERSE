import assert from 'node:assert/strict';
import test from 'node:test';
import { buildAuthRedirect, safeNextPath } from '../src/lib/authRedirect.ts';
import { safeExternalUrl } from '../src/lib/safeUrl.ts';

test('authentication return paths stay inside the SPA', () => {
  assert.equal(safeNextPath('/drama/projects/3?tab=canvas#node-1'), '/drama/projects/3?tab=canvas#node-1');
  assert.equal(safeNextPath('https://attacker.invalid/'), '/');
  assert.equal(safeNextPath('//attacker.invalid/'), '/');
  assert.equal(buildAuthRedirect('/drama/projects/3?tab=canvas#node-1'), '/auth?next=%2Fdrama%2Fprojects%2F3%3Ftab%3Dcanvas%23node-1');
});

test('new-window URLs accept only HTTP(S)', () => {
  assert.equal(safeExternalUrl('https://pay.example.test/checkout?id=1'), 'https://pay.example.test/checkout?id=1');
  assert.equal(safeExternalUrl('javascript:alert(1)'), '');
  assert.equal(safeExternalUrl('data:text/html,payload'), '');
});
