import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

function loadBalance() {
  const source = readFileSync(new URL('../src/lib/balanceAdjustment.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  new Function('module', 'exports', code)(module, module.exports);
  return module.exports;
}

function loadQueryState() {
  const source = readFileSync(new URL('../src/lib/adminQueryState.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  new Function('module', 'exports', code)(module, module.exports);
  return module.exports;
}

test('balance adjustment carries an expected balance snapshot and idempotency key', () => {
  const { buildBalanceAdjustment } = loadBalance();
  assert.deepEqual(buildBalanceAdjustment('12.30', 'decrease', 5000, 'manual correction', 'req-1'), {
    balance_delta_fen: -1230,
    balance_note: 'manual correction',
    balance_request_id: 'req-1',
    expected_balance_fen: 5000,
  });
});

test('balance adjustment rejects unsafe amount, empty note and int32 overflow', () => {
  const { buildBalanceAdjustment } = loadBalance();
  assert.throws(() => buildBalanceAdjustment('0', 'increase', 1, 'x', 'req'), /大于 0/);
  assert.throws(() => buildBalanceAdjustment('1', 'increase', 1, '', 'req'), /调账原因/);
  assert.throws(() => buildBalanceAdjustment('1', 'increase', 2_147_483_647, 'x', 'req'), /上限|不能超过/);
});

test('admin query updates batch same-tick changes without dropping parameters', async () => {
  const { updateAdminQuery } = loadQueryState();
  const location = {};
  const navigations = [];
  const navigate = (params, options) => navigations.push([params.toString(), options.replace]);
  updateAdminQuery(location, '?page=4&q=film', (params) => params.set('page', '1'), navigate);
  updateAdminQuery(location, '?page=4&q=film', (params) => params.set('page_size', '50'), navigate);
  await new Promise((resolve) => queueMicrotask(resolve));
  assert.deepEqual(navigations, [['page=1&q=film&page_size=50', true]]);
});
