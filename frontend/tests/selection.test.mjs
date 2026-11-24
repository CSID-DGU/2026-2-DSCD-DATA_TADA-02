import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleCandidate, cardScrollTarget, cardWindow } from '../src/selection.mjs';

const five = ['a', 'b', 'c', 'd', 'e'];

test('fifth selection is accepted and sixth is rejected until a candidate is removed', () => {
  const four = five.slice(0, 4);
  const selected = toggleCandidate(four, 'e');
  assert.deepEqual(selected, five);
  assert.throws(() => toggleCandidate(selected, 'f'), /최대 5개/);
  assert.deepEqual(toggleCandidate(toggleCandidate(selected, 'b'), 'f'), ['a', 'c', 'd', 'e', 'f']);
  assert.deepEqual(four, ['a', 'b', 'c', 'd']);
});

test('card offsets reach the fifth candidate at every display width and stop at the edges', () => {
  const step = 270.25;
  for (const columns of [1, 2, 3]) {
    const lastOffset = (five.length - columns) * step;
    let position = 0;
    for (let i = 1; i <= five.length - columns; i++) {
      position = cardScrollTarget(position, step, lastOffset, 1);
      assert.equal(position, i * step);
    }
    assert.equal(cardScrollTarget(position, step, lastOffset, 1), lastOffset);
    assert.equal(cardScrollTarget(0, step, lastOffset, -1), 0);
  }
  assert.equal(cardScrollTarget(390, 270, 810), 270);
  assert.equal(cardScrollTarget(420, 270, 810), 540);
  assert.equal(cardScrollTarget(539.75, 270, 539.75, 1), 539.75);
  assert.equal(cardScrollTarget(0, 0, 0, 1), 0);
});

test('the slide bar follows the visible range and adjusts to the viewport', () => {
  assert.deepEqual(cardWindow(0, 370, 740, 5), { start: 0, lastStart: 2, total: 5 });
  assert.deepEqual(cardWindow(369.75, 370, 740, 5), { start: 1, lastStart: 2, total: 5 });
  assert.deepEqual(cardWindow(740, 370.125, 740, 5), { start: 2, lastStart: 2, total: 5 });
  assert.deepEqual(cardWindow(1110, 370, 1110, 5), { start: 3, lastStart: 3, total: 5 });
  assert.deepEqual(cardWindow(1110, 370, 0, 2), { start: 0, lastStart: 0, total: 2 });
  assert.deepEqual(cardWindow(0, 0, 0, 1), { start: 0, lastStart: 0, total: 1 });
});
