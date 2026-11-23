import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleCandidate, visibleCandidates } from '../src/selection.mjs';

test('fourth selection is rejected while removal and replacement remain possible', () => {
  const three = ['a', 'b', 'c'];
  assert.throws(() => toggleCandidate(three, 'd'), /최대 3개/);
  assert.deepEqual(toggleCandidate(toggleCandidate(three, 'b'), 'd'), ['a', 'c', 'd']);
  assert.deepEqual(three, ['a', 'b', 'c']);
});
test('every candidate is reachable without shrinking three desktop cards', () => {
  const three = ['a', 'b', 'c'];
  const first = visibleCandidates(three, 0, 3);
  const last = visibleCandidates(three, 3, 3);
  assert.deepEqual(first.values, ['a', 'b', 'c']);
  assert.deepEqual(last.values, ['a', 'b', 'c']);
  assert.deepEqual(visibleCandidates(three, 3, 2).values, ['b', 'c']);
  assert.deepEqual(visibleCandidates(three, 3, 1).values, ['c']);
  assert.equal(new Set([...first.values, ...last.values]).size, 3);
  assert.deepEqual(visibleCandidates(['a'], 4, 3).values, ['a']);
});
