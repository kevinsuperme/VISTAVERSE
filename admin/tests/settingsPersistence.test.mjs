import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

function harness(api) {
  const state = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const slot = cursor++;
      if (!(slot in state)) state[slot] = typeof initial === 'function' ? initial() : initial;
      return [state[slot], (next) => { state[slot] = typeof next === 'function' ? next(state[slot]) : next; }];
    },
    useCallback: (callback) => callback,
    useEffect() {},
    useRef: (current) => ({ current }),
  };
  const source = readFileSync(new URL('../src/hooks/useAdminModelSettings.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  const imports = { react, sonner: { toast: { error() {}, success() {} } }, '@/api/client': { api }, '@/lib/permissions': { hasPermission: () => true } };
  new Function('require', 'module', 'exports', compiled)((name) => imports[name], module, module.exports);
  return () => { cursor = 0; return module.exports.useAdminModelSettings(); };
}

test('settings load failure leaves loading state and exposes retryable error', async () => {
  const render = harness(async () => { throw new Error('offline'); });
  await render().load();
  const hook = render();
  assert.equal(hook.loading, false);
  assert.equal(hook.error, 'offline');
});

test('failed settings save returns false and preserves edits for secret-field callers', async () => {
  const render = harness(async (_path, options) => {
    if (options?.method === 'PATCH') throw new Error('save rejected');
    return { public_base_url: 'https://old.example' };
  });
  await render().load();
  render().patchField('public_base_url', 'https://new.example');
  assert.equal(await render().save({ public_base_url: 'https://new.example' }), false);
  assert.equal(render().form.public_base_url, 'https://new.example');
  assert.equal(render().dirty, true);
  assert.equal(render().saving, false);
});

test('successful save uses persisted response and resets dirty without another GET', async () => {
  let gets = 0;
  const render = harness(async (_path, options) => {
    if (options?.method === 'PATCH') return { settings: { public_base_url: 'https://persisted.example' } };
    gets += 1;
    return { public_base_url: 'https://old.example' };
  });
  await render().load();
  render().patchField('public_base_url', 'https://new.example');
  assert.equal(await render().save({ public_base_url: 'https://new.example' }), true);
  assert.equal(render().form.public_base_url, 'https://persisted.example');
  assert.equal(render().dirty, false);
  assert.equal(gets, 1);
  assert.match(render().saveFeedback, /已保存/);
});
