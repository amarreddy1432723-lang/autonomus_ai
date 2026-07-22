'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Copy, Download, ExternalLink } from 'lucide-react';
import styles from './Download.module.css';

type ReleaseDownload = {
  platform: 'windows' | 'macos' | 'linux';
  arch: string;
  kind: string;
  label: string;
  url: string;
  checksum_sha256?: string | null;
  available: boolean;
  status: 'available' | 'pending_release';
  install_command?: string | null;
};

type ReleaseManifest = {
  version: string;
  channel: string;
  signed: boolean;
  notes_url: string;
  downloads: Record<'windows' | 'macos' | 'linux', ReleaseDownload[]>;
};

const FALLBACK_DOWNLOADS: ReleaseManifest = {
  version: 'local',
  channel: 'stable',
  signed: false,
  notes_url: '/docs',
  downloads: {
    windows: [{
      platform: 'windows',
      arch: 'x64',
      kind: 'installer',
      label: 'Windows 64-bit installer',
      url: '/releases/arceus-code-setup.exe',
      checksum_sha256: null,
      available: false,
      status: 'pending_release',
      install_command: 'winget install ArceusCode.ArceusCode',
    }],
    macos: [
      { platform: 'macos', arch: 'arm64', kind: 'dmg', label: 'Apple Silicon DMG', url: '/releases/arceus-code-mac-arm64.dmg', checksum_sha256: null, available: false, status: 'pending_release', install_command: 'brew install --cask arceus-code' },
      { platform: 'macos', arch: 'x64', kind: 'dmg', label: 'Intel DMG', url: '/releases/arceus-code-mac-x64.dmg', checksum_sha256: null, available: false, status: 'pending_release', install_command: 'brew install --cask arceus-code' },
    ],
    linux: [
      { platform: 'linux', arch: 'x64', kind: 'appimage', label: 'Linux AppImage', url: '/releases/arceus-code-x86_64.AppImage', checksum_sha256: null, available: false, status: 'pending_release' },
      { platform: 'linux', arch: 'x64', kind: 'deb', label: 'Debian / Ubuntu package', url: '/releases/arceus-code_amd64.deb', checksum_sha256: null, available: false, status: 'pending_release' },
      { platform: 'linux', arch: 'x64', kind: 'rpm', label: 'RedHat / Fedora package', url: '/releases/arceus-code.rpm', checksum_sha256: null, available: false, status: 'pending_release' },
    ],
  },
};

async function fetchReleaseManifest(): Promise<ReleaseManifest> {
  const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL?.replace(/\/$/, '');
  const urls = ['/api/v1/downloads/latest', agentUrl ? `${agentUrl}/api/v1/downloads/latest` : null].filter(Boolean) as string[];
  let lastError: unknown = null;
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return (await response.json()) as ReleaseManifest;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Release manifest unavailable');
}

function pickDownload(manifest: ReleaseManifest, platform: 'windows' | 'macos' | 'linux', kind: string, arch?: string): ReleaseDownload {
  return (
    manifest.downloads[platform]?.find((item) => item.kind === kind && (!arch || item.arch === arch)) ||
    FALLBACK_DOWNLOADS.downloads[platform].find((item) => item.kind === kind && (!arch || item.arch === arch)) ||
    FALLBACK_DOWNLOADS.downloads[platform][0]
  );
}

function DownloadAction({ item, primary = false }: { item: ReleaseDownload; primary?: boolean }) {
  const disabled = !item.available;
  return (
    <a
      className={primary ? styles.primaryDownload : styles.secondaryDownload}
      href={disabled ? undefined : item.url}
      aria-disabled={disabled}
      title={disabled ? 'Release artifact is not published yet.' : item.label}
    >
      <Download size={17} />
      {disabled ? 'Installer pending release' : item.label}
    </a>
  );
}

export default function DownloadPage() {
  const [selectedOS, setSelectedOS] = useState<'windows' | 'macos' | 'linux'>('windows');
  const [manifest, setManifest] = useState<ReleaseManifest>(FALLBACK_DOWNLOADS);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const osParam = params.get('os');
    if (osParam === 'windows' || osParam === 'macos' || osParam === 'linux') {
      setSelectedOS(osParam);
      return;
    }
    const ua = window.navigator.userAgent.toLowerCase();
    if (ua.includes('mac')) setSelectedOS('macos');
    else if (ua.includes('linux')) setSelectedOS('linux');
    else setSelectedOS('windows');
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchReleaseManifest()
      .then((payload) => {
        if (!cancelled) {
          setManifest(payload);
          setReleaseError(null);
        }
      })
      .catch((error) => {
        if (!cancelled) setReleaseError(error instanceof Error ? error.message : 'Release manifest unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const downloads = useMemo(() => ({
    windowsInstaller: pickDownload(manifest, 'windows', 'installer', 'x64'),
    macArm: pickDownload(manifest, 'macos', 'dmg', 'arm64'),
    macIntel: pickDownload(manifest, 'macos', 'dmg', 'x64'),
    linuxAppImage: pickDownload(manifest, 'linux', 'appimage', 'x64'),
    linuxDeb: pickDownload(manifest, 'linux', 'deb', 'x64'),
    linuxRpm: pickDownload(manifest, 'linux', 'rpm', 'x64'),
  }), [manifest]);

  const primaryItem = selectedOS === 'windows' ? downloads.windowsInstaller : selectedOS === 'macos' ? downloads.macArm : downloads.linuxAppImage;
  const checksum = primaryItem.checksum_sha256 || 'pending signed release artifact';

  const copyChecksum = async () => {
    if (!primaryItem.checksum_sha256 || typeof navigator === 'undefined') return;
    await navigator.clipboard.writeText(primaryItem.checksum_sha256);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <main className={styles.page}>
      <section className={styles.container}>
        <Link className={styles.backLink} href="/products/code">
          <ArrowLeft size={15} />
          Back to Arceus Code
        </Link>

        <header className={styles.hero}>
          <p>Arceus Code</p>
          <h1>AI engineering workspace for your projects.</h1>
          <span>Download the desktop app, sign in, open a repository, and start your first mission.</span>
        </header>

        <div className={styles.tabs} role="tablist" aria-label="Operating systems">
          {[
            { id: 'windows', label: 'Windows' },
            { id: 'macos', label: 'macOS' },
            { id: 'linux', label: 'Linux' },
          ].map((tab) => (
            <button key={tab.id} type="button" data-active={selectedOS === tab.id} onClick={() => setSelectedOS(tab.id as 'windows' | 'macos' | 'linux')}>
              {tab.label}
            </button>
          ))}
        </div>

        <section className={styles.downloadGrid}>
          <article className={styles.downloadCard}>
            <div className={styles.cardHeader}>
              <h2>Download for {selectedOS === 'windows' ? 'Windows' : selectedOS === 'macos' ? 'macOS' : 'Linux'}</h2>
              <span>{manifest.version} · {manifest.channel}</span>
            </div>

            {releaseError && <p className={styles.warning}>Release manifest unavailable: {releaseError}</p>}
            {!manifest.downloads[selectedOS]?.some((item) => item.available) && (
              <p className={styles.warning}>No published artifact is configured for this platform yet.</p>
            )}

            <DownloadAction item={primaryItem} primary />

            <dl className={styles.metadata}>
              <div><dt>Version</dt><dd>{manifest.version}</dd></div>
              <div><dt>Signing</dt><dd>{manifest.signed ? 'Signed release' : 'Unsigned/local metadata'}</dd></div>
              <div><dt>System</dt><dd>{selectedOS === 'windows' ? 'Windows 10/11 · 64-bit' : selectedOS === 'macos' ? 'macOS · Apple Silicon or Intel' : 'Linux · x64'}</dd></div>
            </dl>

            <div className={styles.checksum}>
              <span>SHA-256</span>
              <code>{checksum}</code>
              <button type="button" onClick={copyChecksum} disabled={!primaryItem.checksum_sha256}>
                {copied ? <CheckCircle2 size={15} /> : <Copy size={15} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>

            {selectedOS === 'macos' && (
              <div className={styles.altDownloads}>
                <DownloadAction item={downloads.macIntel} />
              </div>
            )}
            {selectedOS === 'linux' && (
              <div className={styles.altDownloads}>
                <DownloadAction item={downloads.linuxDeb} />
                <DownloadAction item={downloads.linuxRpm} />
              </div>
            )}
          </article>

          <aside className={styles.installCard}>
            <h2>Install in five steps</h2>
            <ol>
              <li>Download the installer for your operating system.</li>
              <li>Install Arceus Code and launch the desktop app.</li>
              <li>Sign in or connect your account.</li>
              <li>Open or clone a repository.</li>
              <li>Start your first mission.</li>
            </ol>
            <Link className={styles.releaseNotes} href={manifest.notes_url || '/docs'}>
              View release notes
              <ExternalLink size={14} />
            </Link>
          </aside>
        </section>
      </section>
    </main>
  );
}
