'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Calendar.module.css';
import { ChevronLeft, ChevronRight } from 'lucide-react';

type CalendarEvent = {
  title: string;
  type: string;
};

type CalendarDay = {
  key: string;
  num: number | string;
  events: CalendarEvent[];
  isToday: boolean;
};

export default function CalendarPage() {
  const [view, setView] = useState<'month' | 'week' | 'day'>('month');
  const [monthOffset, setMonthOffset] = useState(0);
  const { data: schedules = [] } = useQuery({
    queryKey: ['calendar-schedules'],
    queryFn: async () => apiRequest('/api/v1/schedules?is_active=true&page_size=100')
  });

  const weekdayNames = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
  const now = new Date();
  const activeMonth = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
  const monthLabel = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(activeMonth);
  const daysInMonth = new Date(activeMonth.getFullYear(), activeMonth.getMonth() + 1, 0).getDate();
  const mondayStartOffset = (activeMonth.getDay() + 6) % 7;
  const dayCells: CalendarDay[] = [
    ...Array.from({ length: mondayStartOffset }, (_, index) => ({ key: `pad-${index}`, num: '', events: [], isToday: false })),
    ...Array.from({ length: daysInMonth }, (_, index) => {
      const date = new Date(activeMonth.getFullYear(), activeMonth.getMonth(), index + 1);
      const dateKey = date.toDateString();
      const events = schedules
        .filter((schedule: any) => schedule.next_run_at && new Date(schedule.next_run_at).toDateString() === dateKey)
        .map((schedule: any) => ({ title: schedule.title, type: schedule.schedule_type === 'ai' ? 'ai' : 'task' }));
      return {
        key: date.toISOString(),
        num: index + 1,
        events,
        isToday: date.toDateString() === now.toDateString(),
      };
    })
  ];
  const visibleDays: CalendarDay[] = view === 'month'
    ? dayCells
    : view === 'week'
      ? dayCells.filter((day) => day.num && Math.ceil(Number(day.num) / 7) === Math.ceil(now.getDate() / 7))
      : dayCells.filter((day) => day.isToday);

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Work Schedule Calendar</h1>
        </div>

        <div className={styles.calendarCard}>
          <div className={styles.viewToggle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button className={styles.iconButton} onClick={() => setMonthOffset((value) => value - 1)} aria-label="Previous month"><ChevronLeft size={16} /></button>
              <span className={styles.dateTitle}>{monthLabel}</span>
              <button className={styles.iconButton} onClick={() => setMonthOffset((value) => value + 1)} aria-label="Next month"><ChevronRight size={16} /></button>
            </div>
            
            <div className={styles.btnGroup}>
              <button className={`${styles.btnToggle} ${view === 'month' ? styles.btnToggleActive : ''}`} onClick={() => setView('month')}>Month</button>
              <button className={`${styles.btnToggle} ${view === 'week' ? styles.btnToggleActive : ''}`} onClick={() => setView('week')}>Week</button>
              <button className={`${styles.btnToggle} ${view === 'day' ? styles.btnToggleActive : ''}`} onClick={() => setView('day')}>Day</button>
            </div>
          </div>

          <div className={styles.grid}>
            {weekdayNames.map((name) => (
              <div key={name} className={styles.dayHeader}>{name}</div>
            ))}
            
            {visibleDays.map((day) => (
              <div key={day.key} className={`${styles.dayCell} ${day.isToday ? styles.dayCellToday : ''}`}>
                <span className={`${styles.dayNumber} ${day.isToday ? styles.dayNumberToday : ''}`}>{day.num}</span>
                {day.events.map((e, index) => (
                  <div 
                    key={index} 
                    className={`${styles.event} ${
                      e.type === 'task' ? styles.eventTask : e.type === 'ai' ? styles.eventAI : styles.eventMeeting
                    }`}
                  >
                    {e.title}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
