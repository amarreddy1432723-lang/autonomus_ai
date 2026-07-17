export type ErrorClass =
  | 'quota_exceeded'    // 402 response
  | 'api_offline'       // fetch failed / ECONNREFUSED
  | 'model_error'       // LLM provider returned error
  | 'file_too_large'    // file > size limit
  | 'patch_conflict'    // apply failed due to conflict
  | 'command_failed'    // shell command non-zero exit
  | 'auth_error'        // 401/403
  | 'rate_limited'      // 429
  | 'unknown';          // everything else

export interface ClassifiedError {
  class: ErrorClass;
  message: string;      // human-readable cause
  hint: string;         // what user should do next
  raw?: string;         // original error.message
}

export function classifyError(error: unknown, statusCode?: number): ClassifiedError {
  const msg = error instanceof Error ? error.message : String(error || '');
  const status = statusCode ?? (error as any)?.status;

  if (status === 402 || msg.includes('QUOTA_EXCEEDED') || msg.includes('quota') || msg.includes('limit reached')) {
    return {
      class: 'quota_exceeded',
      message: 'Usage limit reached',
      hint: 'Upgrade your plan or wait for monthly reset',
      raw: msg,
    };
  }
  if (status === 429 || msg.includes('rate limit') || msg.includes('rate_limit')) {
    return {
      class: 'rate_limited',
      message: 'Too many requests',
      hint: 'Wait 30 seconds and try again',
      raw: msg,
    };
  }
  if (status === 401 || status === 403) {
    return {
      class: 'auth_error',
      message: 'Authentication required',
      hint: 'Connect your Arceus account inside the desktop app and try again',
      raw: msg,
    };
  }
  if (msg.includes('ECONNREFUSED') || msg.includes('fetch failed') || msg.includes('Failed to fetch') || msg.includes('offline') || msg.includes('NetworkError')) {
    return {
      class: 'api_offline',
      message: 'Agent API is offline',
      hint: 'Retry services. Local folder, editor, and terminal can still work while cloud actions are offline',
      raw: msg,
    };
  }
  if (msg.includes('file too large') || msg.includes('size limit')) {
    return {
      class: 'file_too_large',
      message: 'File is too large',
      hint: 'Split the file or exclude it from context',
      raw: msg,
    };
  }
  if (msg.includes('patch conflict') || msg.includes('apply failed') || msg.includes('hunk')) {
    return {
      class: 'patch_conflict',
      message: 'Patch conflict detected',
      hint: 'Reset the patch and try again after reviewing changes',
      raw: msg,
    };
  }
  if (msg.includes('model') || msg.includes('LLM') || msg.includes('provider') || msg.includes('completion')) {
    return {
      class: 'model_error',
      message: 'AI model error',
      hint: 'Check your API key or try a different model',
      raw: msg,
    };
  }
  if (msg.includes('exit code') || msg.includes('non-zero') || msg.includes('command failed')) {
    return {
      class: 'command_failed',
      message: 'Command exited with error',
      hint: 'Check the terminal for the full error output',
      raw: msg,
    };
  }

  return {
    class: 'unknown',
    message: msg || 'An unexpected error occurred',
    hint: 'Check the Activity panel for details',
    raw: msg,
  };
}
