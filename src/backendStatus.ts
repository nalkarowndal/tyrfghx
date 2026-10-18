import type { StudioStatus } from './api';

/** Shared by polling and explicit restart: only the latest operation may publish. */
export function createBackendStatusLoader(
  status: (value: StudioStatus | null) => void,
  error: (value: string) => void,
  pending: (value: boolean) => void,
) {
  let revision = 0;
  let busy = false;
  return {
    cancel() { revision++; busy = false; },
    async run(load: () => Promise<StudioStatus>, restart = false) {
      if (busy && !restart) return;
      const request = ++revision;
      busy = true;
      pending(true);
      if (restart) { status(null); error(''); }
      try {
        const result = await load();
        if (request === revision) { status(result); error(''); }
      } catch {
        if (request === revision) {
          status(null);
          error(restart
            ? '백엔드를 다시 시작하지 못했습니다. 다른 aiimage 창을 닫고 다시 시도하세요.'
            : 'Python API에 연결하지 못했습니다. 모델 관리는 계속 사용할 수 있습니다.');
        }
      } finally {
        if (request === revision) { busy = false; pending(false); }
      }
    },
  };
}
