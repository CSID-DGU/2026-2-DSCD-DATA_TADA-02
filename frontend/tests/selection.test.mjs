import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleCandidate, visibleCandidates } from '../src/selection.mjs';

test('sixth selection is rejected while removal and replacement remain possible', () => {
  const five = ['a', 'b', 'c', 'd', 'e'];
  assert.throws(() => toggleCandidate(five, 'f'), /5/);
  assert.deepEqual(toggleCandidate(toggleCandidate(five, 'c'), 'f'), ['a', 'b', 'd', 'e', 'f']);
  assert.deepEqual(five, ['a', 'b', 'c', 'd', 'e']);
});
test('every candidate is reachable without shrinking three desktop cards', () => {
  const five = ['a', 'b', 'c', 'd', 'e'];
  const first = visibleCandidates(five, 0, 3);
  const last = visibleCandidates(five, 3, 3);
  assert.deepEqual(first.values, ['a', 'b', 'c']);
  assert.deepEqual(last.values, ['c', 'd', 'e']);
  assert.equal(new Set([...first.values, ...last.values]).size, 5);
  assert.deepEqual(visibleCandidates(['a'], 4, 3).values, ['a']);
});
