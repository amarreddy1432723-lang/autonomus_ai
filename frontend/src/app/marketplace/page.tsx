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
  publisher?: string;
  permissions: string[];
  capabilities?: { id: string; kind?: string; health?: string }[];
  verification?: { verified?: boolean; executable?: boolean; reason?: string };
};

type InstalledPlugin = {
  id: string;
  plugin_id?: string;
  status: string;
  executable?: boolean;
  verification?: { verified?: boolean; executable?: boolean; reason?: string };
  capabilities?: { id: string; kind?: string; health?: string }[];
  manifest: MarketplacePlugin & { entry?: string; source?: string };
};

type ExtensionInventory = {
  extensions: { plugin_id: string; name: string; type: string; status: string; executable: boolean }[];
  capabilities: { id: string; kind?: string; health?: string; plugin_name?: string }[];
};

type SdkContract = {
  runtime_version: string;
  languages: string[];
  modules: string[];
  extension_types: string[];
};

export default function MarketplacePage() {
  const [marketplace, setMarketplace] = useState<MarketplacePlugin[]>([]);
  const [installed, setInstalled] = useState<InstalledPlugin[]>([]);
  const [extensions, setExtensions] = useState<ExtensionInventory>({ extensions: [], capabilities: [] });
  const [sdk, setSdk] = useState<SdkContract | null>(null);
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
      const [extensionsResult, sdkResult] = await Promise.all([
        apiRequest('/api/v1/extensions').catch(() => ({ extensions: [], capabilities: [] })),
        apiRequest('/api/v1/sdk').catch(() => null),
      ]);
      setMarketplace(marketplaceResult.plugins || []);
      setInstalled(installedResult.plugins || []);
      setExtensions(extensionsResult || { extensions: [], capabilities: [] });
      setSdk(sdkResult);
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
            <h1>Developer Platform</h1>
            <span className={styles.headerSubcopy}>Install governed connectors, specialists, workflow packs, knowledge packs, UI extensions, and model providers.</span>
          </div>
          <button className={styles.ghostButton} onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </header>

        {message ? <div className={styles.notice}>{message}</div> : null}

        <section className={styles.platformStrip} aria-label="Developer platform status">
          <article>
            <span>Runtime</span>
            <strong>{sdk?.runtime_version || '2.0.0'}</strong>
            <small>Extension API</small>
          </article>
          <article>
            <span>SDK Languages</span>
            <strong>{sdk?.languages?.length || 8}</strong>
            <small>{(sdk?.languages || []).slice(0, 4).join(', ') || 'Python, TypeScript, Go, Rust'}</small>
          </article>
          <article>
            <span>Active Extensions</span>
            <strong>{extensions.extensions.length}</strong>
            <small>Loaded or verified</small>
          </article>
          <article>
            <span>Capabilities</span>
            <strong>{extensions.capabilities.length}</strong>
            <small>Registered providers</small>
          </article>
        </section>

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
                        {plugin.verification?.verified ? <small className={styles.verified}>Verified</small> : null}
                      </div>
                      <p>{plugin.description}</p>
                      <p className={styles.publisher}>Publisher: {plugin.publisher || 'Unknown'} · Capabilities: {plugin.capabilities?.length || 0}</p>
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
                        {plugin.executable ? <small className={styles.verified}>Executable</small> : <small className={styles.blocked}>Review only</small>}
                      </div>
                      <p>{plugin.manifest?.description || 'No description provided.'}</p>
                      <p className={styles.publisher}>{plugin.verification?.reason || 'Governed by Arceus extension policy.'}</p>
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
