'use client';

import { useEffect, useMemo, useState } from 'react';
import AppShell from '@/components/AppShell';
import { apiRequest } from '@/utils/api';
import styles from './page.module.css';

type MarketplacePlugin = {
  id: string;
  name: string;
  version: string;
  description: string;
  type: string;
  permissions: string[];
};

type InstalledPlugin = {
  id: string;
  status: string;
  manifest: MarketplacePlugin & { entry?: string; source?: string };
};

export default function MarketplacePage() {
  const [marketplace, setMarketplace] = useState<MarketplacePlugin[]>([]);
  const [installed, setInstalled] = useState<InstalledPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  const installedByName = useMemo(() => {
    const map = new Map<string, InstalledPlugin>();
    installed.forEach((plugin) => map.set(plugin.manifest?.name, plugin));
    return map;
  }, [installed]);

  async function refresh() {
    setLoading(true);
    setMessage('');
    try {
      const [marketplaceResult, installedResult] = await Promise.all([
        apiRequest('/api/v1/plugins/marketplace'),
        apiRequest('/api/v1/plugins'),
      ]);
      setMarketplace(marketplaceResult.plugins || []);
      setInstalled(installedResult.plugins || []);
    } catch (error: any) {
      setMessage(error?.message || 'Could not load plugins.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function install(plugin: MarketplacePlugin) {
    setMessage('');
    try {
      await apiRequest('/api/v1/plugins/install', {
        method: 'POST',
        body: JSON.stringify({
          manifest: {
            ...plugin,
            entry: plugin.type === 'panel' ? 'panel/index.js' : 'plugin.py',
            source: 'marketplace',
          },
        }),
      });
      await refresh();
    } catch (error: any) {
      setMessage(error?.message || 'Install failed.');
    }
  }

  async function setStatus(pluginId: string, status: string) {
    setMessage('');
    try {
      await apiRequest(`/api/v1/plugins/${pluginId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      await refresh();
    } catch (error: any) {
      setMessage(error?.message || 'Plugin update failed.');
    }
  }

  async function uninstall(pluginId: string) {
    setMessage('');
    try {
      await apiRequest(`/api/v1/plugins/${pluginId}`, { method: 'DELETE' });
      await refresh();
    } catch (error: any) {
      setMessage(error?.message || 'Uninstall failed.');
    }
  }

  return (
    <AppShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <div>
            <p className={styles.kicker}>Arceus SDK</p>
            <h1>Plugin Marketplace</h1>
          </div>
          <button className={styles.ghostButton} onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </header>

        {message ? <div className={styles.notice}>{message}</div> : null}

        <section className={styles.grid}>
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h2>Marketplace</h2>
              <span>{marketplace.length} available</span>
            </div>
            <div className={styles.list}>
              {marketplace.map((plugin) => {
                const installedPlugin = installedByName.get(plugin.name);
                return (
                  <article className={styles.pluginRow} key={plugin.id}>
                    <div>
                      <div className={styles.rowTitle}>
                        <strong>{plugin.name}</strong>
                        <span>{plugin.version}</span>
                        <small>{plugin.type.replace('_', ' ')}</small>
                      </div>
                      <p>{plugin.description}</p>
                      <div className={styles.chips}>
                        {plugin.permissions.map((permission) => (
                          <span key={permission}>{permission}</span>
                        ))}
                      </div>
                    </div>
                    <button
                      className={installedPlugin ? styles.secondaryButton : styles.primaryButton}
                      onClick={() => install(plugin)}
                    >
                      {installedPlugin ? 'Update' : 'Install'}
                    </button>
                  </article>
                );
              })}
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h2>My Plugins</h2>
              <span>{installed.length} installed</span>
            </div>
            <div className={styles.list}>
              {installed.length === 0 ? (
                <div className={styles.empty}>Install a plugin to add skills, panels, or tools to Arceus Code.</div>
              ) : (
                installed.map((plugin) => (
                  <article className={styles.installedRow} key={plugin.id}>
                    <div>
                      <div className={styles.rowTitle}>
                        <strong>{plugin.manifest?.name}</strong>
                        <span className={styles.status}>{plugin.status}</span>
                      </div>
                      <p>{plugin.manifest?.description || 'No description provided.'}</p>
                    </div>
                    <div className={styles.actions}>
                      {plugin.status === 'active' ? (
                        <button className={styles.secondaryButton} onClick={() => setStatus(plugin.id, 'disabled')}>
                          Disable
                        </button>
                      ) : (
                        <button className={styles.secondaryButton} onClick={() => setStatus(plugin.id, 'active')}>
                          Enable
                        </button>
                      )}
                      <button className={styles.dangerButton} onClick={() => uninstall(plugin.id)}>
                        Uninstall
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
