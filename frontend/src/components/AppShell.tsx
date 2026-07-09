'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { 
  CheckSquare,
  Calendar, ShieldAlert,
  Settings, ChevronLeft, ChevronRight, Bell, Search, Activity, Cpu, X, Code2,
  LogIn, UserPlus, LogOut, Mic, Sparkles, Lightbulb, PanelLeft, BriefcaseBusiness
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
  
  const [activityCollapsed, setActivityCollapsed] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [productMenuOpen, setProductMenuOpen] = useState(false);
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

  const products = useMemo(() => [
    { label: 'Product Hub', href: '/hub', match: ['/hub'], icon: Sparkles },
    { label: 'NEXUS Code', href: '/workspace', match: ['/workspace', '/studio', '/chat', '/design', '/deploy', '/internet', '/intelligence'], icon: Code2 },
    { label: 'NEXUS PA', href: '/pa', match: ['/pa', '/calendar', '/tasks', '/timeline'], icon: BriefcaseBusiness },
    { label: 'NEXUS Interview', href: '/interview', match: ['/interview'], icon: Mic },
    { label: 'Settings', href: '/settings', match: ['/settings'], icon: Settings },
  ], []);

  const allNavItems = useMemo(() => [
    { label: 'Hub', icon: Sparkles, href: '/hub' },
    { label: 'NEXUS Code', icon: Code2, href: '/workspace' },
    { label: 'NEXUS PA', icon: BriefcaseBusiness, href: '/pa' },
    { label: 'NEXUS Interview', icon: Mic, href: '/interview' },
    { label: 'Settings', icon: Settings, href: '/settings' },
  ], []);

  const activeProduct = products.find((product) => product.match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) || products[0];

  const sidebarItems = useMemo(() => {
    if (activeProduct.label === 'NEXUS PA') {
      return [
        { label: 'PA Home', icon: BriefcaseBusiness, href: '/pa' },
        { label: 'Planner', icon: Calendar, href: '/pa/planner' },
        { label: 'Tasks', icon: CheckSquare, href: '/tasks' },
        { label: 'Calendar', icon: Calendar, href: '/calendar' },
        { label: 'Reflection', icon: Lightbulb, href: '/pa/reflection' },
      ];
    }
    if (activeProduct.label === 'NEXUS Interview') {
      return [{ label: 'NEXUS Interview', icon: Mic, href: '/interview' }];
    }
    if (activeProduct.label === 'Settings') {
      return [{ label: 'Settings', icon: Settings, href: '/settings' }];
    }
    if (activeProduct.label === 'Product Hub') {
      return [
        { label: 'Hub', icon: Sparkles, href: '/hub' },
        { label: 'NEXUS Code', icon: Code2, href: '/workspace' },
        { label: 'NEXUS PA', icon: BriefcaseBusiness, href: '/pa' },
        { label: 'NEXUS Interview', icon: Mic, href: '/interview' },
      ];
    }
    return [
      { label: 'Workspace', icon: Code2, href: '/workspace' },
      { label: 'Approvals', icon: ShieldAlert, href: '/approvals', badge: pendingApprovalCount },
    ];
  }, [activeProduct.label, pendingApprovalCount]);

  const currentItem = allNavItems.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)) || allNavItems[0];

  const commands = useMemo(() => [
    { id: 'quick-code', label: 'Ask NEXUS Code', hint: 'Ctrl+J', action: () => router.push('/workspace') },
    { id: 'quick-design', label: 'Design in NEXUS Code', hint: 'Ctrl+D', action: () => router.push('/workspace?agent=design') },
    { id: 'quick-deploy', label: 'Deploy from NEXUS Code', hint: 'Ctrl+Shift+D', action: () => router.push('/workspace?agent=deploy') },
    { id: 'quick-research', label: 'Research in NEXUS Code', hint: 'Ctrl+R', action: () => router.push('/workspace?agent=research') },
    { id: 'toggle-sidebar', label: 'Toggle Sidebar', hint: 'Ctrl+B', action: () => toggleSidebar() },
    ...allNavItems.map((item, index) => ({
      id: item.href,
      label: `Open ${item.label}`,
      hint: index < 9 ? `${index + 1}` : '',
      action: () => router.push(item.href),
    })),
    { id: 'memory-search', label: 'Search memory', hint: 'Enter', action: () => searchQuery.trim() && router.push(`/memory?query=${encodeURIComponent(searchQuery.trim())}`) },
  ], [allNavItems, router, searchQuery, toggleSidebar]);

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
      if (modifier && event.key.toLowerCase() === 'b') {
        event.preventDefault();
        toggleSidebar();
      }
      if (modifier && event.key.toLowerCase() === 'j') {
        event.preventDefault();
        router.push('/workspace');
      }
      if (modifier && event.key.toLowerCase() === 'g') {
        event.preventDefault();
        router.push('/workspace');
      }
      if (modifier && event.key.toLowerCase() === 'd') {
        event.preventDefault();
        router.push(event.shiftKey ? '/workspace?agent=deploy' : '/workspace?agent=design');
      }
      if (modifier && event.key.toLowerCase() === 'r') {
        event.preventDefault();
        router.push('/workspace?agent=research');
      }
      if (!modifier && /^[1-9]$/.test(event.key)) {
        const item = allNavItems[Number(event.key) - 1];
        if (item) router.push(item.href);
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [allNavItems, router, toggleSidebar]);

  const runCommand = (action: () => void) => {
    action();
    setPaletteOpen(false);
  };

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <button 
            onClick={toggleSidebar} 
            className={styles.iconButton} 
            title={sidebarCollapsed ? "Show sidebar (Ctrl+B)" : "Hide sidebar (Ctrl+B)"}
            aria-label="Toggle sidebar"
            style={{ border: 'none', background: 'transparent', padding: '0 4px', cursor: 'pointer' }}
          >
            <PanelLeft size={16} />
          </button>
          <button
            type="button"
            className={styles.logoArea}
            aria-label="Open product switcher"
            onClick={() => setProductMenuOpen((value) => !value)}
            style={{ border: 'none', background: 'transparent', cursor: 'pointer' }}
          >
            <Cpu className={styles.logoGlow} size={20} />
            <span>NEXUS</span>
          </button>
          {productMenuOpen && (
            <div className={styles.productMenu}>
              {products.map((product) => {
                const Icon = product.icon;
                return (
                  <button key={product.label} type="button" onClick={() => { setProductMenuOpen(false); router.push(product.href); }}>
                    <Icon size={16} />
                    <span>{product.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className={styles.breadcrumb} aria-label="Current location">
          <Link href={activeProduct.href}>{activeProduct.label}</Link>
          <ChevronRight size={13} />
          <span>{currentItem.label}</span>
        </div>
        
        <div className={styles.searchBar}>
          <Search size={14} color="var(--color-text-secondary)" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Ask, search, or run a command..."
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
          <span className={styles.searchShortcut}>Ctrl K</span>
        </div>
        
        <div className={styles.topbarActions}>
          <div className={styles.statusDots} title="Auth, goals, and agent services online">
            <span className={styles.statusDot} />
            <span className={styles.statusDot} />
            <span className={styles.statusDot} />
          </div>

          <button 
            onClick={() => setActivityCollapsed(!activityCollapsed)}
            className={styles.iconButton}
            title="Agent activity"
            aria-label="Toggle agent activity"
          >
            <Activity size={16} />
          </button>

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
          <div className={styles.notificationBell}>
            <Bell size={18} />
            {pendingApprovalCount > 0 && (
              <span className={styles.notificationBadge}>{pendingApprovalCount}</span>
            )}
          </div>
          {!(typeof window !== 'undefined' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) && isDemoSignedIn && (
            <div className={styles.avatar} title="Demo User">DU</div>
          )}
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <div className={styles.mainContainer}>
        <aside className={`${styles.sidebar} ${sidebarCollapsed ? styles.sidebarCollapsed : ''}`} onDoubleClick={toggleSidebar}>
          <ul className={styles.navItems}>
            {sidebarItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname.startsWith(item.href);
              return (
                <li key={item.label}>
                  <Link 
                    href={item.href} 
                    className={`${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
                    title={item.label}
                    aria-label={item.label}
                  >
                    <Icon size={18} />
                    <span className={styles.navTooltip}>{item.label}</span>
                    {item.badge !== undefined && item.badge > 0 && (
                      <span className={styles.navBadge}>
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
              <span>Agent Activity</span>
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
