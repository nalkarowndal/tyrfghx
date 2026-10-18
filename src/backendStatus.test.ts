import { expect, it } from 'vitest';
import { createBackendStatusLoader } from './backendStatus';
import type { StudioStatus } from './api';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const connected: StudioStatus = { app: 'aiimage', version: '0.1.0', mode: 'foundation', engines: [] };

it('never restores old connected state when refresh overlaps a failed restart', async () => {
  let shown: StudioStatus | null = null;
  let error = '';
  const loader = createBackendStatusLoader(value => { shown = value; }, value => { error = value; }, () => {});
  const old = deferred<StudioStatus>();
  const retry = deferred<StudioStatus>();
  const polling = loader.run(() => old.promise);
  const restarting = loader.run(() => retry.promise, true);
  old.resolve(connected);
  await polling;
  expect(shown).toBeNull();
  retry.reject(new Error('private error'));
  await restarting;
  expect(shown).toBeNull();
  expect(error).toContain('다시 시작하지 못했습니다');
  expect(error).not.toContain('private');
});

it('ignores late errors after successful restart and skips polling while busy', async () => {
  let shown: StudioStatus | null = null;
  let error = '';
  const loader = createBackendStatusLoader(value => { shown = value; }, value => { error = value; }, () => {});
  const old = deferred<StudioStatus>();
  const pending = loader.run(() => old.promise);
  await loader.run(() => { throw new Error('must not poll while busy'); });
  await loader.run(async () => connected, true);
  old.reject(new Error('old failure'));
  await pending;
  expect(shown).toBe(connected);
  expect(error).toBe('');
});

it('does not update an unmounted view', async () => {
  let shown: StudioStatus | null = null;
  const loader = createBackendStatusLoader(value => { shown = value; }, () => {}, () => {});
  const old = deferred<StudioStatus>();
  const pending = loader.run(() => old.promise);
  loader.cancel();
  old.resolve(connected);
  await pending;
  expect(shown).toBeNull();
});
