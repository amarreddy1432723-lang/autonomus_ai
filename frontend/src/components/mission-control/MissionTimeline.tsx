import styles from './MissionControlProduct.module.css';
import type { MissionControlEvent } from './types';
import { TimelineEvent } from './TimelineEvent';

const FALLBACK_EVENTS: MissionControlEvent[] = [
  { eventId: 'ready', eventType: 'mission.ready', payload: { title: 'Mission Control is ready' } },
  { eventId: 'waiting', eventType: 'task.assignment.created', payload: { role: 'Mission Lead', task_key: 'next.approved.task' } },
];

const FILTERS = ['All', 'Scheduler', 'Worker', 'Repository', 'Verification', 'Recovery'] as const;

function matchesFilter(event: MissionControlEvent, filter: string) {
  if (filter === 'All') return true;
  const haystack = `${event.eventType || ''} ${event.actorType || ''}`.toLowerCase();
  return haystack.includes(filter.toLowerCase());
}

export function MissionTimeline({
  events,
  filter = 'All',
  onFilterChange,
}: {
  events: MissionControlEvent[];
  filter?: string;
  onFilterChange?: (filter: string) => void;
}) {
  const visibleEvents = events.length > 0 ? events.slice(0, 8) : FALLBACK_EVENTS;
  const filteredEvents = visibleEvents.filter((event) => matchesFilter(event, filter));

  return (
    <section className={styles.panel} aria-label="Mission timeline">
      <header>
        <div>
          <h3>Live Timeline</h3>
          <p>Every material runtime event, translated into founder-readable language.</p>
        </div>
        <span className={styles.taskBadge}>{filteredEvents.length} events</span>
      </header>
      <div className={styles.timelineFilters}>
        {FILTERS.map((item) => (
          <button key={item} type="button" data-active={filter === item} onClick={() => onFilterChange?.(item)}>
            {item}
          </button>
        ))}
      </div>
      <div className={styles.timeline}>
        {filteredEvents.length === 0 && <div className={styles.empty}>No events match this filter.</div>}
        {filteredEvents.map((event, index) => (
          <TimelineEvent key={event.eventId || `${event.eventType}-${index}`} event={event} />
        ))}
      </div>
    </section>
  );
}
