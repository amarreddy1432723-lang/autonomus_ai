'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, MessageSquare, Target, CheckSquare, 
  BrainCircuit, Calendar, Hourglass, ShieldAlert, BarChart3, 
  Settings, ChevronLeft, ChevronRight, Bell, Search, Activity, Cpu
} from 'lucide-react';
import { useAppStore } from '../store';
import styles from './AppShell.module.css';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { 
    sidebarCollapsed, toggleSidebar, 
    agentActivityFeed, pendingApprovalCount 
  } = useAppStore();
  
  const [activityCollapsed, setActivityCollapsed] = useState(false);

  const navItems = [
    { label: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
    { label: 'Chat', icon: MessageSquare, href: '/chat' },
    { label: 'Goals', icon: Target, href: '/goals' },
    { label: 'Tasks', icon: CheckSquare, href: '/tasks' },
    { label: 'Memory', icon: BrainCircuit, href: '/memory' },
    { label: 'Calendar', icon: Calendar, href: '/calendar' },
    { label: 'Timeline', icon: Hourglass, href: '/timeline' },
    { label: 'Approvals', icon: ShieldAlert, href: '/approvals', badge: pendingApprovalCount },
    { label: 'Analytics', icon: BarChart3, href: '/analytics' },
    { label: 'Settings', icon: Settings, href: '/settings' },
  ];

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
          <input type="text" placeholder="Search goals, memories... ⌘K" readOnly />
          <span className={styles.searchShortcut}>⌘K</span>
        </div>
        
        <div className={styles.topbarActions}>
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
          
          <div className={styles.avatar}>AM</div>
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
    </div>
  );
}
