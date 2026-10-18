import { afterEach, expect, it, vi } from 'vitest';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { getStatus } from './api';
import { restartBackend } from './nativeBackend';

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn(), isTauri: vi.fn() }));
afterEach(() => { vi.resetAllMocks(); vi.unstubAllGlobals(); });

it('routes packaged desktop status through IPC without exposing a token or URL', async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValueOnce(true).mockResolvedValueOnce({ app: 'aiimage', engines: [] });
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  expect((await getStatus()).app).toBe('aiimage');
  expect(invoke).toHaveBeenNthCalledWith(2, 'backend_status');
  expect(fetch).not.toHaveBeenCalled();
});

it('does not fall back to an unauthenticated service when the managed API fails', async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValueOnce(true).mockRejectedValueOnce('backend_start_failed');
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  await expect(getStatus()).rejects.toBe('backend_start_failed');
  expect(fetch).not.toHaveBeenCalled();
});

it('keeps explicit browser development status requests', async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ app: 'aiimage' }) });
  vi.stubGlobal('fetch', fetch);
  await getStatus();
  expect(fetch).toHaveBeenCalledOnce();
  expect(invoke).not.toHaveBeenCalled();
});

it('restarts only through a fixed native command with no user paths', async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue({ app: 'aiimage', engines: [] });
  await restartBackend();
  expect(invoke).toHaveBeenCalledExactlyOnceWith('restart_backend');
});

it('rejects restart from the browser', async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  await expect(restartBackend()).rejects.toThrow();
  expect(invoke).not.toHaveBeenCalled();
});
