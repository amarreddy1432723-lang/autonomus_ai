'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { 
  LayoutDashboard, MessageSquare, Target, CheckSquare, 
  BrainCircuit, Calendar, Hourglass, ShieldAlert, BarChart3, 
  Settings, ChevronLeft, ChevronRight, Bell, Search, Activity, Cpu, X, Code2,
  LogIn, UserPlus, LogOut, Mic
} from 'lucide-react';
import { UserButton, useAuth } from '@clerk/nextjs';
import { useAppStore } from '../store';
import styles from './AppShell.module.css';

function ClerkUserSection() {
  const { isSignedIn } = useAuth();
  if (isSignedIn) {
    return (
      <div className={styles.avatar}>
        <UserButton />
      </div>
    );
  }
  return (
    <>
      <Link href="/sign-in" className={styles.authLink}>
        <LogIn size={15} />
        <span>Login</span>
      </Link>
      <Link href="/sign-up" className={`${styles.authLink} ${styles.authLinkPrimary}`}>
        <UserPlus size={15} />
        <span>Sign up</span>
      </Link>
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { 
    sidebarCollapsed, toggleSidebar, 
    agentActivityFeed, pendingApprovalCount 
  } = useAppStore();
  
  const [activityCollapsed, setActivityCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [isDemoSignedIn, setIsDemoSignedIn] = useState(false);

  useEffect(() => {
    const hasDemoCookie = typeof document !== 'undefined' && document.cookie.includes('my-ai.mock_token');
    setIsDemoSignedIn(hasDemoCookie);
  }, []);

  const handleDemoSignOut = () => {
    document.cookie = 'my-ai.mock_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    setIsDemoSignedIn(false);
    router.push('/sign-in');
  };

  const navItems = useMemo(() => [
    { label: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
    { label: 'Chat', icon: MessageSquare, href: '/chat' },
    { label: 'Interview', icon: Mic, href: '/interview' },
    { label: 'Workspace', icon: Code2, href: '/workspace' },
    { label: 'Goals', icon: Target, href: '/goals' },
    { label: 'Tasks', icon: CheckSquare, href: '/tasks' },
    { label: 'Memory', icon: BrainCircuit, href: '/memory' },
    { label: 'Calendar', icon: Calendar, href: '/calendar' },
    { label: 'Timeline', icon: Hourglass, href: '/timeline' },
    { label: 'Approvals', icon: ShieldAlert, href: '/approvals', badge: pendingApprovalCount },
    { label: 'Analytics', icon: BarChart3, href: '/analytics' },
    { label: 'Settings', icon: Settings, href: '/settings' },
  ], [pendingApprovalCount]);

  const commands = useMemo(() => [
    ...navItems.map((item, index) => ({
      id: item.href,
      label: item.label,
      hint: index < 9 ? `${index + 1}` : '',
      action: () => router.push(item.href),
    })),
    { id: 'new-goal', label: 'Create a new goal', hint: 'Ctrl+G', action: () => router.push('/goals?new=1') },
    { id: 'chat', label: 'Open chat with AI', hint: 'Ctrl+J', action: () => router.push('/chat') },
    { id: 'memory-search', label: 'Search memory', hint: 'Enter', action: () => searchQuery.trim() && router.push(`/memory?query=${encodeURIComponent(searchQuery.trim())}`) },
  ], [navItems, router, searchQuery]);

  const filteredCommands = commands.filter((command) => (
    !searchQuery.trim() || command.label.toLowerCase().includes(searchQuery.trim().toLowerCase())
  ));

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 0);
      }
      if (modifier && event.key.toLowerCase() === 'j') {
        event.preventDefault();
        router.push('/chat');
      }
      if (modifier && event.key.toLowerCase() === 'g') {
        event.preventDefault();
        router.push('/goals?new=1');
      }
      if (!modifier && /^[1-9]$/.test(event.key)) {
        const item = navItems[Number(event.key) - 1];
        if (item) router.push(item.href);
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navItems, router]);

  const runCommand = (action: () => void) => {
    action();
    setPaletteOpen(false);
  };

  return (
    <div className={styles.shell}>
      {/* TOPBAR */}
      <header className={styles.topbar}>
        <div className={styles.logoArea}>
          <Cpu className={styles.logoGlow} size={20} />
          <span>my-<span className={styles.logoGlow}>ai</span></span>
        </div>
        
        <div className={styles.searchBar}>
          <Search size={14} color="var(--color-text-secondary)" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search goals, memories... Ctrl+K"
            value={searchQuery}
            onFocus={() => setPaletteOpen(true)}
            onChange={(event) => {
              setSearchQuery(event.target.value);
              setPaletteOpen(true);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && searchQuery.trim()) {
                router.push(`/memory?query=${encodeURIComponent(searchQuery.trim())}`);
                setPaletteOpen(false);
              }
            }}
          />
          <span className={styles.searchShortcut}>⌘K</span>
        </div>
        
        <div className={styles.topbarActions}>
          {typeof window !== 'undefined' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? (
            <ClerkUserSection />
          ) : (
            <>
              {isDemoSignedIn ? (
                <button 
                  onClick={handleDemoSignOut}
                  className={styles.authLink}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <LogOut size={15} />
                  <span>Sign out</span>
                </button>
              ) : (
                <>
                  <Link href="/sign-in" className={styles.authLink}>
                    <LogIn size={15} />
                    <span>Login</span>
                  </Link>
                  <Link href="/sign-up" className={`${styles.authLink} ${styles.authLinkPrimary}`}>
                    <UserPlus size={15} />
                    <span>Sign up</span>
                  </Link>
                </>
              )}
            </>
          )}

          <div className={styles.agentIndicator}>
            <span className={styles.pulseDot} />
            <span>AI Online</span>
          </div>
          
          <div className={styles.notificationBell}>
            <Bell size={18} />
            {pendingApprovalCount > 0 && (
              <span className={styles.notificationBadge}>{pendingApprovalCount}</span>
            )}
          </div>
          
          <button 
            onClick={() => setActivityCollapsed(!activityCollapsed)}
            style={{ background: 'none', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            title="Toggle Agent Activity Ticker"
          >
            <Activity size={18} />
          </button>
          
          {!(typeof window !== 'undefined' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) && isDemoSignedIn && (
            <div className={styles.avatar} title="Demo User">DU</div>
          )}
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <div className={styles.mainContainer}>
        {/* SIDEBAR */}
        <aside className={`${styles.sidebar} ${sidebarCollapsed ? styles.sidebarCollapsed : ''}`}>
          <ul className={styles.navItems}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname.startsWith(item.href);
              return (
                <li key={item.label}>
                  <Link 
                    href={item.href} 
                    className={`${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
                    title={sidebarCollapsed ? item.label : undefined}
                  >
                    <Icon size={18} />
                    {!sidebarCollapsed && (
                      <span style={{ flex: 1 }}>{item.label}</span>
                    )}
                    {!sidebarCollapsed && item.badge !== undefined && item.badge > 0 && (
                      <span style={{ 
                        backgroundColor: 'var(--color-error)', 
                        color: 'white', 
                        fontSize: '10px', 
                        padding: '1px 6px', 
                        borderRadius: 'var(--radius-full)'
                      }}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
          
          <button className={styles.sidebarCollapseBtn} onClick={toggleSidebar}>
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            {!sidebarCollapsed && <span>Collapse Sidebar</span>}
          </button>
        </aside>

        {/* CONTENT & ACTIVITY BAR */}
        <div className={styles.contentWrapper}>
          <main className={styles.mainContent}>
            {children}
          </main>
          
          {/* RIGHT AGENT ACTIVITY TICKER */}
          <aside className={`${styles.activityBar} ${activityCollapsed ? styles.activityBarCollapsed : ''}`}>
            <div className={styles.activityHeader}>
              <span>Agent Activity Ticker</span>
              <button 
                onClick={() => setActivityCollapsed(true)} 
                style={{ background: 'none', border: 'none', color: 'var(--color-text-tertiary)', cursor: 'pointer' }}
              >
                ×
              </button>
            </div>
            <div className={styles.activityList}>
              {agentActivityFeed.map((event) => (
                <div key={event.id} className={styles.activityItem}>
                  <div className={styles.activityAgent}>
                    <Cpu size={12} />
                    <span>{event.agent}</span>
                  </div>
                  <div className={styles.activityText}>{event.activity}</div>
                  <div className={styles.activityTime}>{event.timestamp}</div>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </div>

      {paletteOpen && (
        <div className={styles.paletteOverlay} role="dialog" aria-modal="true" aria-label="Command palette">
          <div className={styles.palette}>
            <div className={styles.paletteHeader}>
              <Search size={16} />
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Type a command or search memory"
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && filteredCommands[0]) {
                    runCommand(filteredCommands[0].action);
                  }
                }}
              />
              <button type="button" className={styles.iconButton} onClick={() => setPaletteOpen(false)} aria-label="Close command palette">
                <X size={16} />
              </button>
            </div>
            <div className={styles.paletteList}>
              {filteredCommands.slice(0, 8).map((command) => (
                <button key={command.id} type="button" className={styles.paletteItem} onClick={() => runCommand(command.action)}>
                  <span>{command.label}</span>
                  {command.hint && <kbd>{command.hint}</kbd>}
                </button>
              ))}
              {filteredCommands.length === 0 && (
                <div className={styles.paletteEmpty}>No matching commands</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
