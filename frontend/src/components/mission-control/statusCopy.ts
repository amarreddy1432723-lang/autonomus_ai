export function missionStatusLabel(status?: string) {
  switch (status) {
    case 'awaiting_approval':
      return 'Waiting for approval';
    case 'queued':
      return 'Preparing agents';
    case 'running':
      return 'Agents working';
    case 'verifying':
      return 'Verifying changes';
    case 'attention_required':
      return 'Needs your attention';
    case 'completed':
      return 'Mission completed';
    case 'failed':
      return 'Mission stopped';
    case 'cancelled':
      return 'Cancelled';
    default:
      return status ? status.replace(/_/g, ' ') : 'Not started';
  }
}

export function taskStatusLabel(status?: string) {
  switch (status) {
    case 'blocked':
      return 'Blocked';
    case 'ready':
      return 'Ready';
    case 'assigned':
    case 'scheduled':
      return 'Scheduled';
    case 'running':
    case 'accepted':
      return 'Running';
    case 'review_required':
    case 'reviewing':
      return 'Review required';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    case 'cancelled':
      return 'Cancelled';
    default:
      return status ? status.replace(/_/g, ' ') : 'Waiting';
  }
}

export function eventCopy(eventType?: string, payload: Record<string, unknown> = {}) {
  const task = String(payload.task_key || payload.taskKey || payload.task_id || '').trim();
  const role = String(payload.role || payload.worker_role || payload.worker_id || 'Agent').trim();
  switch (eventType) {
    case 'task.assignment.created':
      return `${role} assigned${task ? ` to ${task}` : ''}`;
    case 'task.assignment.accepted':
      return `${role} started${task ? ` ${task}` : ' the task'}`;
    case 'task.assignment.released':
      return `${role} released the task`;
    case 'assignment.completed':
      return `Task completed${task ? `: ${task}` : ''}`;
    case 'assignment.failed':
      return `Task needs attention${task ? `: ${task}` : ''}`;
    case 'assignment.recovery.reported':
      return 'Recovery report received';
    case 'path.reservation.acquired':
      return 'Repository files reserved safely';
    case 'path.reservation.released':
      return 'Repository reservation released';
    case 'tool.completed':
      return 'Repository inspection completed';
    case 'change_set.created':
    case 'task.change_set.recorded':
    case 'arceus.task.change_set.recorded':
      return 'Changes ready for review';
    case 'verification.completed':
      return 'Verification completed';
    default:
      return eventType ? eventType.replace(/[._]/g, ' ') : 'Mission activity recorded';
  }
}

export function formatDuration(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '0:00';
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

export function heartbeatLabel(ageSeconds?: number | null) {
  if (ageSeconds == null) return 'Waiting';
  if (ageSeconds < 45) return 'Healthy';
  if (ageSeconds < 120) return 'Delayed';
  return 'Stale';
}
