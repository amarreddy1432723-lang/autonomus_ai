'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Bell,
  Calendar,
  CheckCircle2,
  Clock,
  Lock,
  Mic,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Zap,
} from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

type PAItem = {
  id: string;
  title: string;
  body?: string;
  type?: string;
  status?: string;
  next_run_at?: string | null;
  due_date?: string | null;
  read_at?: string | null;
  priority_score?: number;
  content?: string;
};

type PAToday = {
  locked?: boolean;
  state?: string;
  status_label?: string;
  monitoring?: boolean;
  daily_brief?: string;
  tasks?: PAItem[];
  reminders?: PAItem[];
  automations?: PAItem[];
  notifications?: PAItem[];
  memories?: PAItem[];
  context_used?: Record<string, number>;
  unread_alerts?: number;
  active_schedules?: number;
  pending_delegations?: number;
  access?: { plan?: string; reason?: string; upgrade_target?: string };
};

const formatTime = (value?: string | null) => {
  if (!value) return 'No time';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'No time';
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export default function PAPage() {
  const [today, setToday] = useState<PAToday | null>(null);
  const [loading, setLoading] = useState(true);
  const [command, setCommand] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [reminderTitle, setReminderTitle] = useState('');
  const [automationTitle, setAutomationTitle] = useState('');
  const [message, setMessage] = useState('');
  const [listening, setListening] = useState(false);

  const locked = !!today?.locked;
  const isPaused = today?.state === 'paused' || today?.state === 'stopped';
  const contextCount = useMemo(
    () => Object.values(today?.context_used || {}).reduce((sum, value) => sum + Number(value || 0), 0),
    [today?.context_used]
  );

  const loadToday = async () => {
    setLoading(true);
    try {
      setToday(await apiRequest('/api/v1/pa/today'));
      setMessage('');
    } catch (error: any) {
      const detail = String(error?.message || '');
      if (detail.includes('NEXUS PA requires')) {
        setToday({ locked: true, access: { reason: 'pa_requires_pro', upgrade_target: 'pro' } });
      } else {
        setMessage(detail || 'Could not load NEXUS PA.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadToday();
  }, []);

  const runCommand = async () => {
    if (!command.trim()) return;
    const text = command;
    setCommand('');
    setMessage('Working...');
    try {
      const result = await apiRequest('/api/v1/pa/command', {
        method: 'POST',
        body: JSON.stringify({ command: text }),
      });
      setMessage(result.message || result.type?.replaceAll('_', ' ') || 'Done.');
      await loadToday();
    } catch (error: any) {
      setMessage(error?.message || 'Command failed.');
    }
  };

  const createTask = async () => {
    if (!taskTitle.trim()) return;
    await apiRequest('/api/v1/pa/tasks', {
      method: 'POST',
      body: JSON.stringify({ title: taskTitle, priority_score: 0.7 }),
    });
    setTaskTitle('');
    await loadToday();
  };

  const createReminder = async () => {
    if (!reminderTitle.trim()) return;
    await apiRequest('/api/v1/pa/reminders', {
      method: 'POST',
      body: JSON.stringify({ title: reminderTitle, permission: 'confirm' }),
    });
    setReminderTitle('');
    await loadToday();
  };

  const createAutomation = async () => {
    if (!automationTitle.trim()) return;
    await apiRequest('/api/v1/pa/automations', {
      method: 'POST',
      body: JSON.stringify({ title: automationTitle, trigger: 'recurring', permission: 'confirm' }),
    });
    setAutomationTitle('');
    await loadToday();
  };

  const togglePause = async () => {
    await apiRequest(isPaused ? '/api/v1/pa/resume' : '/api/v1/pa/pause', { method: 'POST' });
    await loadToday();
  };

  const markTaskDone = async (id: string) => {
    await apiRequest(`/api/v1/pa/tasks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'done' }),
    });
    await loadToday();
  };

  const markNotificationRead = async (id: string) => {
    await apiRequest(`/api/v1/pa/notifications/${id}/read`, { method: 'POST' });
    await loadToday();
  };

  const startVoice = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessage('Voice input is not supported in this browser. Type the command instead.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => setListening(true);
    recognition.onerror = () => {
      setListening(false);
      setMessage('Voice permission was blocked or interrupted.');
    };
    recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => {
      const text = event.results?.[0]?.[0]?.transcript || '';
      setCommand(text);
    };
    recognition.start();
  };

  if (locked) {
    return (
      <AppShell>
        <main className={styles.page}>
          <section className={styles.lockPanel}>
            <Lock size={34} />
            <h1>NEXUS PA requires Pro</h1>
            <p>Unlock the personal OS: tasks, reminders, automations, command center, memory context, and phone-ready daily brief.</p>
            <Link className={styles.button} href="/settings">Open settings</Link>
          </section>
        </main>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.osTopBar}>
          <div>
            <span className={styles.eyebrow}>NEXUS PA OS</span>
            <h1 className={styles.compactTitle}>What needs attention?</h1>
          </div>
          <div className={styles.osControls}>
            <span className={`${styles.statusPill} ${styles[`status_${today?.state || 'active'}`] || ''}`}>
              <span className={styles.statusDot} />
              {today?.status_label || 'Active'}
            </span>
            <button className={styles.secondaryButton} onClick={loadToday} type="button"><RefreshCw size={15} /> Refresh</button>
            <button className={isPaused ? styles.button : styles.dangerButton} onClick={togglePause} type="button">
              {isPaused ? <PlayCircle size={15} /> : <PauseCircle size={15} />}
              {isPaused ? 'Resume' : 'Pause'}
            </button>
          </div>
        </section>

        <section className={styles.paCommandCenter}>
          <div>
            <span className={styles.eyebrow}>Command</span>
            <h2 className={styles.compactTitle}>Ask, plan, remind</h2>
          </div>
          <label className={styles.paCommandInput}>
            <Search size={16} />
            <input
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') runCommand();
              }}
              placeholder="Create task, schedule reminder, summarize today, search memory..."
            />
          </label>
          <button className={styles.voiceButton} type="button" onClick={startVoice}>
            <Mic size={16} />
            {listening ? 'Listening' : 'Voice'}
          </button>
        </section>

        {message && <div className={styles.errorStrip}>{message}</div>}

        <section className={styles.paStatusStrip}>
          <div className={styles.statusMetric}><CheckCircle2 size={16} /><span>{today?.pending_delegations || 0} open tasks</span></div>
          <div className={styles.statusMetric}><Bell size={16} /><span>{today?.unread_alerts || 0} alerts</span></div>
          <div className={styles.statusMetric}><Zap size={16} /><span>{today?.active_schedules || 0} active schedules</span></div>
          <div className={styles.statusMetric}><ShieldAlert size={16} /><span>{contextCount} context signals</span></div>
        </section>

        <section className={styles.dailyBriefPanel}>
          <div>
            <span className={styles.eyebrow}>Today brief</span>
            <p>{loading ? 'Loading your day...' : today?.daily_brief || 'No brief available yet.'}</p>
          </div>
          <div className={styles.briefStats}>
            <span>Plan {today?.access?.plan || 'pro'}</span>
            <span>Voice local</span>
            <span>No cross-product auto-read</span>
          </div>
        </section>

        <section className={styles.paOsGrid}>
          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Priority Tasks</h2>
              <CheckCircle2 size={17} />
            </div>
            <div className={styles.paMiniForm}>
              <input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Add a task..." />
              <button onClick={createTask} type="button">Add</button>
            </div>
            <div className={styles.phaseList}>
              {(today?.tasks || []).map((task) => (
                <div className={styles.item} key={task.id}>
                  <strong>{task.title}</strong>
                  <p>{task.status || 'queued'} · due {formatTime(task.due_date)}</p>
                  <button className={styles.tinyButton} onClick={() => markTaskDone(task.id)} type="button">Done</button>
                </div>
              ))}
              {!today?.tasks?.length && <p className={styles.meta}>No open PA tasks.</p>}
            </div>
          </div>

          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Reminders</h2>
              <Clock size={17} />
            </div>
            <div className={styles.paMiniForm}>
              <input value={reminderTitle} onChange={(event) => setReminderTitle(event.target.value)} placeholder="Remind me to..." />
              <button onClick={createReminder} type="button">Set</button>
            </div>
            <div className={styles.phaseList}>
              {(today?.reminders || []).map((reminder) => (
                <div className={styles.item} key={reminder.id}>
                  <strong>{reminder.title}</strong>
                  <p>{reminder.status} · {formatTime(reminder.next_run_at)}</p>
                </div>
              ))}
              {!today?.reminders?.length && <p className={styles.meta}>No reminders scheduled.</p>}
            </div>
          </div>

          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Automations</h2>
              <Zap size={17} />
            </div>
            <div className={styles.paMiniForm}>
              <input value={automationTitle} onChange={(event) => setAutomationTitle(event.target.value)} placeholder="Daily brief, follow-up, meeting prep..." />
              <button onClick={createAutomation} type="button">Draft</button>
            </div>
            <div className={styles.phaseList}>
              {(today?.automations || []).map((automation) => (
                <div className={styles.item} key={automation.id}>
                  <strong>{automation.title}</strong>
                  <p>{automation.status} · confirmation required</p>
                </div>
              ))}
              {!today?.automations?.length && <p className={styles.meta}>Create a safe automation draft.</p>}
            </div>
          </div>

          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Notifications</h2>
              <Bell size={17} />
            </div>
            <div className={styles.phaseList}>
              {(today?.notifications || []).map((item) => (
                <div className={styles.item} key={item.id}>
                  <strong>{item.title}</strong>
                  <p>{item.body}</p>
                  {!item.read_at && <button className={styles.tinyButton} onClick={() => markNotificationRead(item.id)} type="button">Mark read</button>}
                </div>
              ))}
              {!today?.notifications?.length && <p className={styles.meta}>No unread attention items.</p>}
            </div>
          </div>

          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Memory Context</h2>
              <Sparkles size={17} />
            </div>
            <div className={styles.phaseList}>
              {(today?.memories || []).map((memory) => (
                <div className={styles.item} key={memory.id}>
                  <strong>{memory.type || 'memory'}</strong>
                  <p>{memory.content}</p>
                </div>
              ))}
              {!today?.memories?.length && <p className={styles.meta}>Save memories to make PA more useful.</p>}
            </div>
          </div>

          <div className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <h2>Calendar Ready</h2>
              <Calendar size={17} />
            </div>
            <p>Google and Outlook connectors stay integration-gated. PA can prepare meetings once a calendar is connected.</p>
            <div className={styles.inlineActions}>
              <Link className={styles.secondaryButton} href="/settings">Integrations</Link>
              <Link className={styles.secondaryButton} href="/pa/planner">Planner</Link>
            </div>
          </div>
        </section>

        <nav className={styles.mobilePaDock} aria-label="NEXUS PA mobile navigation">
          <Link href="/pa"><Sparkles size={17} /> Today</Link>
          <Link href="/tasks"><CheckCircle2 size={17} /> Tasks</Link>
          <Link href="/calendar"><Calendar size={17} /> Calendar</Link>
          <Link href="/memory"><Search size={17} /> Memory</Link>
        </nav>
      </main>
    </AppShell>
  );
}
