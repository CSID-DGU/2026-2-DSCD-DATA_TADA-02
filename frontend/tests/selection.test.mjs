import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleCandidate, visibleCandidates } from '../src/selection.mjs';

const five = ['a', 'b', 'c', 'd', 'e'];

test('fifth selection is accepted and sixth is rejected until a candidate is removed', () => {
  const four = five.slice(0, 4);
  const selected = toggleCandidate(four, 'e');
  assert.deepEqual(selected, five);
  assert.throws(() => toggleCandidate(selected, 'f'), /최대 5개/);
  assert.deepEqual(toggleCandidate(toggleCandidate(selected, 'b'), 'f'), ['a', 'c', 'd', 'e', 'f']);
  assert.deepEqual(four, ['a', 'b', 'c', 'd']);
});

test('all five candidates are reachable at each card display width', () => {
  for (const width of [1, 2, 3]) {
    const pages = five.map((_, offset) => visibleCandidates(five, offset, width).values);
    assert.deepEqual([...new Set(pages.flat())], five);
    assert.ok(pages.every(page => page.length === width));
    assert.deepEqual(pages.at(-1), five.slice(-width));
  }
  assert.deepEqual(visibleCandidates(['a'], 4, 3).values, ['a']);
});
