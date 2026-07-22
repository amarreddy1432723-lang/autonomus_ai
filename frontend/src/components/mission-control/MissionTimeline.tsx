import styles from './MissionControlProduct.module.css';
import type { MissionControlEvent } from './types';
import { TimelineEvent } from './TimelineEvent';

const FALLBACK_EVENTS: MissionControlEvent[] = [
  { eventId: 'ready', eventType: 'mission.ready', payload: { title: 'Mission Control is ready' } },
  { eventId: 'waiting', eventType: 'task.assignment.created', payload: { role: 'Mission Lead', task_key: 'next.approved.task' } },
];

export function MissionTimeline({ events }: { events: MissionControlEvent[] }) {
  const visibleEvents = events.length > 0 ? events.slice(0, 8) : FALLBACK_EVENTS;

  return (
    <section className={styles.panel} aria-label="Mission timeline">
      <header>
        <div>
          <h3>Live Timeline</h3>
          <p>Every material runtime event, translated into founder-readable language.</p>
        </div>
        <span className={styles.taskBadge}>{visibleEvents.length} events</span>
      </header>
      <div className={styles.timeline}>
        {visibleEvents.map((event, index) => (
          <TimelineEvent key={event.eventId || `${event.eventType}-${index}`} event={event} />
        ))}
      </div>
    </section>
  );
}
