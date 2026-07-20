export interface ArceusError {
  code: string;
  message: string;
  status: number;
  requestId?: string;
  retryable: boolean;
  fieldErrors?: Record<string, string>;
  details?: unknown;
}

export class ArceusApiError extends Error implements ArceusError {
  code: string;
  status: number;
  requestId?: string;
  retryable: boolean;
  fieldErrors?: Record<string, string>;
  details?: unknown;

  constructor(error: ArceusError) {
    super(error.message);
    this.name = 'ArceusApiError';
    this.code = error.code;
    this.status = error.status;
    this.requestId = error.requestId;
    this.retryable = error.retryable;
    this.fieldErrors = error.fieldErrors;
    this.details = error.details;
  }
}

export function normalizeApiError(input: {
  status: number;
  statusText?: string;
  payload?: any;
  requestId?: string | null;
}): ArceusError {
  const detail = input.payload?.detail;
  const code =
    detail?.code ||
    detail?.error_class ||
    input.payload?.code ||
    input.payload?.error ||
    statusCodeToErrorCode(input.status);
  const message =
    typeof detail === 'string'
      ? detail
      : detail?.message || input.payload?.message || input.statusText || 'API request failed';
  const fieldErrors = detail?.field_errors || input.payload?.field_errors;
  return {
    code,
    message,
    status: input.status,
    requestId: input.requestId || input.payload?.request_id || detail?.request_id,
    retryable: isRetryable(input.status, code),
    fieldErrors,
    details: input.payload,
  };
}

export function normalizeNetworkError(error: unknown): ArceusError {
  const message = error instanceof Error ? error.message : 'Network request failed';
  return {
    code: 'NetworkError',
    message,
    status: 0,
    retryable: true,
    details: error,
  };
}

function statusCodeToErrorCode(status: number) {
  if (status === 401) return 'AuthenticationError';
  if (status === 403) return 'AuthorizationError';
  if (status === 409) return 'ConflictError';
  if (status === 422 || status === 400) return 'ValidationError';
  if (status === 429) return 'RateLimitError';
  if (status >= 500) return 'ProviderError';
  return 'UnknownError';
}

function isRetryable(status: number, code: string) {
  return status === 0 || status === 408 || status === 429 || status >= 500 || code === 'NetworkError';
}

