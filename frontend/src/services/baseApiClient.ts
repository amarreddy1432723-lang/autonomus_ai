import { ArceusApiError, normalizeApiError, normalizeNetworkError } from '@/lib/arceusError';
import { logger } from '@/lib/telemetry';
import { createApiHeadersAsync, getServiceUrl } from '@/utils/api';

export type ApiClientOptions = RequestInit & {
  timeoutMs?: number;
  requestId?: string;
};

export class BaseApiClient {
  async request<T>(path: string, options: ApiClientOptions = {}): Promise<T> {
    const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
    const startedAt = now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000);
    const headers = await createApiHeadersAsync(options);
    const requestId =
      options.requestId ||
      (typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `req_${Date.now()}_${Math.random().toString(16).slice(2)}`);
    headers.set('x-request-id', requestId);

    try {
      const response = await fetch(getServiceUrl(path), {
        ...options,
        headers,
        signal: options.signal || controller.signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new ArceusApiError(
          normalizeApiError({
            status: response.status,
            statusText: response.statusText,
            payload,
            requestId: response.headers.get('x-request-id') || requestId,
          })
        );
      }
      logger.info('api.request.completed', {
        path,
        status: response.status,
        durationMs: Math.round(now() - startedAt),
      });
      if (response.status === 204) return {} as T;
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ArceusApiError) {
        logger.error('api.request.failed', error, { path, status: error.status, retryable: error.retryable });
        throw error;
      }
      const normalized = normalizeNetworkError(error);
      logger.error('api.request.network_failed', error, { path, retryable: normalized.retryable });
      throw new ArceusApiError(normalized);
    } finally {
      clearTimeout(timeout);
    }
  }
}

export const baseApiClient = new BaseApiClient();
