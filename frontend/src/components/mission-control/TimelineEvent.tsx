import styles from './MissionControlProduct.module.css';
import { eventCopy } from './statusCopy';
import type { MissionControlEvent } from './types';

function eventTime(value?: string | null) {
  if (!value) return 'now';
  try {
    return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  } catch {
    return 'now';
  }
}

export function TimelineEvent({ event }: { event: MissionControlEvent }) {
  return (
    <article className={styles.timelineItem}>
      <span className={styles.eventTime}>{eventTime(event.occurredAt)}</span>
      <div>
        <strong>{eventCopy(event.eventType, event.payload)}</strong>
        <small className={styles.muted}>{event.eventType || 'runtime.event'}</small>
        {event.payload && Object.keys(event.payload).length > 0 && (
          <details>
            <summary>Evidence payload</summary>
            <pre>{JSON.stringify(event.payload, null, 2)}</pre>
          </details>
        )}
      </div>
    </article>
  );
}
