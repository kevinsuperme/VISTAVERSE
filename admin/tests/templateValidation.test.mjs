import assert from 'node:assert/strict';
import test from 'node:test';
import { validateTemplate } from '../src/lib/templateValidation.ts';
const valid = { id: 'film', name: 'Film', preview_cover: '/static/cover.png', default_ratio: '16:9', shot_duration_min: 3, shot_duration_max: 8, sort_order: 0 };
test('template validation rejects empty names, invalid durations and unsafe image schemes', () => {
  assert.equal(validateTemplate(valid), null);
  for (const patch of [{ name: ' ' }, { shot_duration_min: 0 }, { shot_duration_min: 9 }, { shot_duration_max: NaN }, { sort_order: 1.5 }, { preview_cover: 'javascript:alert(1)' }, { preview_cover: '//other.example/x' }]) {
    assert.equal(typeof validateTemplate({ ...valid, ...patch }), 'string');
  }
  assert.equal(validateTemplate({ ...valid, preview_cover: 'https://example.com/cover.png' }), null);
});
