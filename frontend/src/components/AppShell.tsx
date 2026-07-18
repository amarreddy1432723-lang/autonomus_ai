'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  ShieldAlert,
  Settings, ChevronLeft, ChevronRight, Bell, Search, Activity, Cpu, X, Code2,
  LogIn, UserPlus, LogOut, PanelLeft, ShieldCheck, MonitorCheck
} from 'lucide-react';
import { UserButton, useAuth } from '@clerk/nextjs';
import { useAppStore } from '../store';
import { isElectronRuntime, probeServiceHealth, serviceHealthCopy, type ServiceHealthSnapshot } from '../utils/serviceHealth';
import styles from './AppShell.module.css';

function useOptionalClerkAuth() {
  try {
    const auth = useAuth();
    return { isSignedIn: auth.isSignedIn === true, clerkReady: true };
  } catch {
    return { isSignedIn: false, clerkReady: false };
  }
}

function ClerkUserSection() {
  const { isSignedIn, clerkReady } = useOptionalClerkAuth();
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

function DesktopAccountSection() {
  const { isSignedIn, clerkReady } = useOptionalClerkAuth();
  const [hasStoredToken, setHasStoredToken] = useState(false);

  useEffect(() => {
    setHasStoredToken(typeof window !== 'undefined' && Boolean(window.localStorage.getItem('my-ai.access_token')));
  }, []);

  if (isSignedIn || hasStoredToken) {
    return (
      isSignedIn && clerkReady ? (
        <div className={styles.avatar}>
          <UserButton />
        </div>
      ) : (
        <Link href="/auth/desktop" className={styles.authLink} title="Refresh desktop account session">
          <MonitorCheck size={15} />
          <span>Connected</span>
        </Link>
      )
    );
  }
  return (
    <Link href="/auth/desktop" className={styles.authLink} title="Connect your Arceus account to enable protected Code actions">
      <MonitorCheck size={15} />
      <span>Connect account</span>
    </Link>
  );
}

function initialElectronState() {
  if (typeof window !== 'undefined') {
    return isElectronRuntime();
  }
  return false;
}

const DESKTOP_ALLOWED_PREFIXES = [
  '/launch',
  '/workspace',
  '/settings',
  '/auth/desktop',
  '/download',
  '/ui-preview',
];

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
  const [clientReady, setClientReady] = useState(false);
  const [isElectron, setIsElectron] = useState(initialElectronState);
  const [serviceHealth, setServiceHealth] = useState<ServiceHealthSnapshot>(() => {
    const state = initialElectronState() ? 'auth_required' : 'partially_online';
    const copy = serviceHealthCopy(state);
    return { state, label: copy.label, detail: copy.detail, online: false, authReady: false, checkedAt: '' };
  });

  const refreshServiceHealth = async () => {
    if (typeof window === 'undefined') return;
    const snapshot = await probeServiceHealth();
    setServiceHealth(snapshot);
  };

  useEffect(() => {
    setClientReady(true);
    const hasDemoCookie = typeof document !== 'undefined' && document.cookie.includes('my-ai.mock_token');
    setIsDemoSignedIn(hasDemoCookie);
    setIsElectron(isElectronRuntime());
  }, []);

  useEffect(() => {
    void refreshServiceHealth();
    const id = window.setInterval(() => void refreshServiceHealth(), 30000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!clientReady || !isElectron) return;
    setProductMenuOpen(false);
    const allowed = DESKTOP_ALLOWED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
    if (!allowed) router.replace('/workspace');
  }, [clientReady, isElectron, pathname, router]);

  const handleDemoSignOut = () => {
    document.cookie = 'my-ai.mock_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    setIsDemoSignedIn(false);
    router.push('/sign-in');
  };

  const products = useMemo(() => {
    const codeProducts = [
      { label: 'Arceus Code', href: '/workspace', match: ['/workspace', '/studio', '/chat', '/design', '/deploy', '/internet', '/intelligence'], icon: Code2 },
      { label: 'Settings', href: '/settings', match: ['/settings'], icon: Settings },
    ];
    return isElectron ? codeProducts : [
      ...codeProducts,
      { label: 'Admin', href: '/admin', match: ['/admin'], icon: ShieldCheck },
    ];
  }, [isElectron]);

  const allNavItems = useMemo(() => {
    const codeItems = [
      { label: 'Arceus Code', icon: Code2, href: '/workspace' },
      { label: 'Settings', icon: Settings, href: '/settings' },
    ];
    return isElectron ? codeItems : [...codeItems, { label: 'Admin', icon: ShieldCheck, href: '/admin' }];
  }, [isElectron]);

  const activeProduct = products.find((product) => product.match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) || products[0];

  const sidebarItems = useMemo(() => {
    if (activeProduct.label === 'Settings') {
      return [{ label: 'Settings', icon: Settings, href: '/settings' }];
    }
    if (activeProduct.label === 'Admin') {
      return [{ label: 'Admin', icon: ShieldCheck, href: '/admin' }];
    }
    if (isElectron) {
      return [
        { label: 'Workspace', icon: Code2, href: '/workspace' },
      ];
    }
    return [
      { label: 'Workspace', icon: Code2, href: '/workspace' },
      { label: 'Approvals', icon: ShieldAlert, href: '/approvals', badge: pendingApprovalCount },
    ];
  }, [activeProduct.label, isElectron, pendingApprovalCount]);

  const currentItem = allNavItems.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)) || allNavItems[0];

  const commands = useMemo(() => [
    { id: 'quick-code', label: 'Ask Arceus Code', hint: 'Ctrl+J', action: () => router.push('/workspace') },
    { id: 'quick-design', label: 'Design in Arceus Code', hint: 'Ctrl+D', action: () => router.push('/workspace?agent=design') },
    { id: 'quick-deploy', label: 'Deploy from Arceus Code', hint: 'Ctrl+Shift+D', action: () => router.push('/workspace?agent=deploy') },
    { id: 'quick-research', label: 'Research in Arceus Code', hint: 'Ctrl+R', action: () => router.push('/workspace?agent=research') },
    { id: 'toggle-sidebar', label: 'Toggle Sidebar', hint: 'Ctrl+B', action: () => toggleSidebar() },
    ...allNavItems.map((item, index) => ({
      id: item.href,
      label: `Open ${item.label}`,
      hint: index < 9 ? `${index + 1}` : '',
      action: () => router.push(item.href),
    })),
    ...(isElectron ? [] : [{ id: 'memory-search', label: 'Search memory', hint: 'Enter', action: () => searchQuery.trim() && router.push(`/memory?query=${encodeURIComponent(searchQuery.trim())}`) }]),
  ], [allNavItems, isElectron, router, searchQuery, toggleSidebar]);

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
            aria-label={isElectron ? 'Open Arceus Code workspace' : 'Open product switcher'}
            onClick={() => {
              if (isElectron) {
                router.push('/workspace');
                return;
              }
              setProductMenuOpen((value) => !value);
            }}
            style={{ border: 'none', background: 'transparent', cursor: 'pointer' }}
          >
            <Cpu className={styles.logoGlow} size={20} />
            <span>{isElectron ? 'Arceus Code' : 'Arceus'}</span>
          </button>
          {!isElectron && productMenuOpen && (
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
                if (isElectron) {
                  const firstCommand = filteredCommands[0];
                  if (firstCommand) {
                    runCommand(firstCommand.action);
                  } else {
                    router.push(`/workspace?query=${encodeURIComponent(searchQuery.trim())}`);
                    setPaletteOpen(false);
                  }
                  return;
                }
                router.push(`/memory?query=${encodeURIComponent(searchQuery.trim())}`);
                setPaletteOpen(false);
              }
            }}
          />
          <span className={styles.searchShortcut}>Ctrl K</span>
        </div>
        
        <div className={styles.topbarActions}>
          <button
            type="button"
            className={styles.serviceStatusPill}
            data-state={serviceHealth.state}
            title={`${serviceHealth.label}: ${serviceHealth.detail}`}
            onClick={() => {
              if (isElectron && serviceHealth.state === 'auth_required') {
                router.push('/auth/desktop');
                return;
              }
              void refreshServiceHealth();
            }}
          >
            <span />
            <strong>{serviceHealth.label}</strong>
          </button>

          {!isElectron && (
            <button 
              onClick={() => setActivityCollapsed(!activityCollapsed)}
              className={styles.iconButton}
              title="Agent activity"
              aria-label="Toggle agent activity"
            >
              <Activity size={16} />
            </button>
          )}

          {isElectron ? (
            <DesktopAccountSection />
          ) : typeof window !== 'undefined' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? (
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
          
          {!isElectron && (
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
          )}
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
                placeholder={isElectron ? 'Type a Code command or search workspace' : 'Type a command or search memory'}
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
