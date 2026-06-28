'use client';

import React from 'react';
import AppShell from '../../components/AppShell';
import styles from './Calendar.module.css';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';

export default function CalendarPage() {
  const days = [
    { num: 22, events: [{ title: 'T2: Auth Svc Coding', type: 'task' }] },
    { num: 23, events: [] },
    { num: 24, events: [{ title: 'Standup briefing', type: 'ai' }] },
    { num: 25, events: [{ title: 'Weekly review', type: 'meeting' }] },
    { num: 26, events: [] },
    { num: 27, events: [] },
    { num: 28, isToday: true, events: [{ title: 'T4: Billing Setup', type: 'task' }, { title: 'Suggest Standup', type: 'ai' }] },
    { num: 29, events: [] }
  ];

  const weekdayNames = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Work Schedule Calendar</h1>
        </div>

        <div className={styles.calendarCard}>
          <div className={styles.viewToggle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button style={{ background: 'none', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer' }}><ChevronLeft size={16} /></button>
              <span className={styles.dateTitle}>June 2026</span>
              <button style={{ background: 'none', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer' }}><ChevronRight size={16} /></button>
            </div>
            
            <div className={styles.btnGroup}>
              <button className={`${styles.btnToggle} ${styles.btnToggleActive}`}>Month</button>
              <button className={styles.btnToggle}>Week</button>
              <button className={styles.btnToggle}>Day</button>
            </div>
          </div>

          <div className={styles.grid}>
            {weekdayNames.map((name) => (
              <div key={name} className={styles.dayHeader}>{name}</div>
            ))}
            
            {/* Pad cells to align with June calendar start */}
            <div className={styles.dayCell}><span className={styles.dayNumber}>15</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>16</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>17</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>18</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>19</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>20</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>21</span></div>

            {days.map((day) => (
              <div key={day.num} className={`${styles.dayCell} ${day.isToday ? styles.dayCellToday : ''}`}>
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
            
            <div className={styles.dayCell}><span className={styles.dayNumber}>30</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>1</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>2</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>3</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>4</span></div>
            <div className={styles.dayCell}><span className={styles.dayNumber}>5</span></div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
