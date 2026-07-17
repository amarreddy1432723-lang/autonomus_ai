'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Download, ArrowLeft, Shield, Monitor, Apple, Terminal, CheckCircle2, ChevronRight, FileCode } from 'lucide-react';
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
      label: 'Windows x64 installer',
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

function downloadBy(manifest: ReleaseManifest, platform: 'windows' | 'macos' | 'linux', kind: string, arch?: string): ReleaseDownload {
  const match = manifest.downloads[platform]?.find((item) => item.kind === kind && (!arch || item.arch === arch));
  const fallback = FALLBACK_DOWNLOADS.downloads[platform].find((item) => item.kind === kind && (!arch || item.arch === arch));
  return match || fallback || FALLBACK_DOWNLOADS.downloads[platform][0];
}

async function fetchReleaseManifest(): Promise<ReleaseManifest> {
  const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL?.replace(/\/$/, '');
  const urls = [
    '/api/v1/downloads/latest',
    agentUrl ? `${agentUrl}/api/v1/downloads/latest` : null,
  ].filter(Boolean) as string[];

  let lastError: unknown = null;
  for (const url of urls) {
    try {
      const response = await fetch(url, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return (await response.json()) as ReleaseManifest;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Release manifest unavailable');
}

function DownloadButton({ item, children, primary = false, compact = false }: { item: ReleaseDownload; children: React.ReactNode; primary?: boolean; compact?: boolean }) {
  const disabled = !item.available;
  const disabledReason = item.status === 'pending_release'
    ? 'Release artifact is not published yet. Configure the download URL and checksum on the backend/Railway release manifest.'
    : 'This download is unavailable.';
  return (
    <a
      href={disabled ? undefined : item.url}
      aria-disabled={disabled}
      aria-label={disabled ? `${item.label} unavailable` : item.label}
      title={disabled ? disabledReason : item.label}
      style={{
        background: primary ? (disabled ? '#2A2F3A' : '#4F8EF7') : '#161B27',
        color: primary && !disabled ? '#08090E' : '#F0F2F5',
        border: primary ? 'none' : '1px solid #1E2535',
        opacity: disabled ? 0.65 : 1,
        pointerEvents: disabled ? 'none' : 'auto',
        padding: compact ? '0.75rem' : '1rem 2rem',
        borderRadius: '8px',
        fontWeight: primary ? '800' : '700',
        fontSize: compact ? '0.9rem' : '1.1rem',
        textDecoration: 'none',
        textAlign: 'center',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.75rem',
        boxShadow: primary && !disabled ? '0 4px 15px rgba(79, 142, 247, 0.3)' : 'none',
        flex: compact ? 1 : undefined,
      }}
    >
      {children}
    </a>
  );
}

export default function DownloadPage() {
  const [selectedOS, setSelectedOS] = useState<'windows' | 'macos' | 'linux'>('windows');
  const [manifest, setManifest] = useState<ReleaseManifest>(FALLBACK_DOWNLOADS);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const osParam = params.get('os');
    if (osParam === 'windows' || osParam === 'macos' || osParam === 'linux') {
      setSelectedOS(osParam);
    } else {
      const ua = window.navigator.userAgent.toLowerCase();
      if (ua.includes('win')) {
        setSelectedOS('windows');
      } else if (ua.includes('mac')) {
        setSelectedOS('macos');
      } else if (ua.includes('linux')) {
        setSelectedOS('linux');
      }
    }
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
        if (!cancelled) {
          setReleaseError(error instanceof Error ? error.message : 'Release manifest unavailable');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const windowsInstaller = downloadBy(manifest, 'windows', 'installer', 'x64');
  const macArm = downloadBy(manifest, 'macos', 'dmg', 'arm64');
  const macIntel = downloadBy(manifest, 'macos', 'dmg', 'x64');
  const linuxAppImage = downloadBy(manifest, 'linux', 'appimage', 'x64');
  const linuxDeb = downloadBy(manifest, 'linux', 'deb', 'x64');
  const linuxRpm = downloadBy(manifest, 'linux', 'rpm', 'x64');

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#08090E',
      color: '#F0F2F5',
      fontFamily: 'Inter, system-ui, sans-serif',
      padding: '4rem 2rem',
      overflowY: 'auto'
    }}>
      {/* Back to Code Page */}
      <div style={{
        maxWidth: '1000px',
        margin: '0 auto 2rem auto',
        padding: '0 1rem'
      }}>
        <Link href="/products/code" style={{
          color: '#8B919E',
          textDecoration: 'none',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          fontSize: '0.95rem'
        }}>
          <ArrowLeft size={16} />
          Back to Arceus Code
        </Link>
      </div>

      <div style={{
        maxWidth: '1000px',
        margin: '0 auto',
        padding: '0 1rem'
      }}>
        <h1 style={{
          fontSize: '2.5rem',
          fontWeight: '900',
          marginBottom: '1rem',
          letterSpacing: '-1.5px'
        }}>
          Get Arceus Code
        </h1>
        <p style={{
          fontSize: '1.1rem',
          color: '#8B919E',
          marginBottom: '3rem',
          maxWidth: '600px'
        }}>
          Install the desktop coding workspace for your system to begin planning, generating, and running tasks natively.
        </p>

        {/* OS Selector Tabs */}
        <div style={{
          display: 'flex',
          gap: '1rem',
          borderBottom: '1px solid #1E2535',
          marginBottom: '3rem',
          paddingBottom: '1px'
        }}>
          {[
            { id: 'windows', label: 'Windows' },
            { id: 'macos', label: 'macOS' },
            { id: 'linux', label: 'Linux' }
          ].map((tab) => {
            const active = selectedOS === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setSelectedOS(tab.id as any)}
                style={{
                  background: 'none',
                  border: 'none',
                  borderBottom: active ? '2px solid #4F8EF7' : '2px solid transparent',
                  color: active ? '#F0F2F5' : '#8B919E',
                  padding: '1rem 1.5rem',
                  fontSize: '1.1rem',
                  fontWeight: active ? '700' : '500',
                  cursor: 'pointer',
                  outline: 'none',
                  transition: 'all 0.2s ease'
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Active OS Installer Actions */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '3rem',
          alignItems: 'start'
        }}>
          {/* Downloads Card */}
          <div style={{
            background: '#0F1117',
            border: '1px solid #1E2535',
            borderRadius: '12px',
            padding: '2.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '2rem'
          }}>
            <h3 style={{ fontSize: '1.5rem', fontWeight: '800' }}>
              Download for {selectedOS === 'windows' ? 'Windows' : selectedOS === 'macos' ? 'macOS' : 'Linux'}
            </h3>
            <div style={{
              background: '#08090E',
              border: '1px solid #1E2535',
              borderRadius: '8px',
              padding: '0.85rem',
              color: '#AAB2C0',
              fontSize: '0.85rem',
              display: 'grid',
              gap: '0.35rem'
            }}>
              <span>Version <strong style={{ color: '#F0F2F5' }}>{manifest.version}</strong> · {manifest.channel} · {manifest.signed ? 'signed installers' : 'unsigned/local build metadata'}</span>
              {releaseError ? (
                <span style={{ color: '#FFB86B' }}>Release manifest unavailable: {releaseError}</span>
              ) : null}
              {!manifest.downloads[selectedOS]?.some((item) => item.available) ? (
                <span style={{ color: '#FFB86B' }}>No published artifact is configured for this platform yet. Set release download URLs before launch.</span>
              ) : null}
            </div>

            {selectedOS === 'windows' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <DownloadButton item={windowsInstaller} primary>
                  <Download size={20} />
                  {windowsInstaller.available ? 'Download Installer (.exe)' : 'Installer unavailable - release artifact missing'}
                </DownloadButton>
                <div style={{ color: '#8B919E', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <span>SHA-256 Checksum: <code>{windowsInstaller.checksum_sha256 || 'pending signed release artifact'}</code></span>
                  <span>Alternatively, install via Winget:</span>
                  <pre style={{
                    background: '#08090E',
                    padding: '0.75rem',
                    borderRadius: '6px',
                    color: '#F0F2F5',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    border: '1px solid #1E2535'
                  }}>{windowsInstaller.install_command || 'winget install ArceusCode.ArceusCode'}</pre>
                </div>
              </div>
            )}

            {selectedOS === 'macos' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <DownloadButton item={macArm} primary compact>
                    <span style={{ fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Download size={16} /> Apple Silicon</span>
                    <span style={{ fontSize: '0.75rem', fontWeight: '500', opacity: 0.8 }}>(M1/M2/M3 .dmg)</span>
                  </DownloadButton>
                  <DownloadButton item={macIntel} compact>
                    <span style={{ fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Download size={16} /> Intel Chip</span>
                    <span style={{ fontSize: '0.75rem', fontWeight: '500', opacity: 0.8 }}>(Intel .dmg)</span>
                  </DownloadButton>
                </div>
                <div style={{ color: '#8B919E', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <span>Gatekeeper Notarized: {manifest.signed ? 'Yes (Apple Developer ID signed)' : 'Pending signing/notarization'}</span>
                  <span>Install via Homebrew:</span>
                  <pre style={{
                    background: '#08090E',
                    padding: '0.75rem',
                    borderRadius: '6px',
                    color: '#F0F2F5',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    border: '1px solid #1E2535'
                  }}>{macArm.install_command || 'brew install --cask arceus-code'}</pre>
                </div>
              </div>
            )}

            {selectedOS === 'linux' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <DownloadButton item={linuxAppImage} primary>
                  <Download size={20} />
                  {linuxAppImage.available ? 'Download AppImage' : 'AppImage pending release'}
                </DownloadButton>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <DownloadButton item={linuxDeb} compact>
                    Debian / Ubuntu (.deb)
                  </DownloadButton>
                  <DownloadButton item={linuxRpm} compact>
                    RedHat / Fedora (.rpm)
                  </DownloadButton>
                </div>
              </div>
            )}
          </div>

          {/* Installation Instructions Card */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <h3 style={{ fontSize: '1.3rem', fontWeight: '800' }}>
              How to Install
            </h3>

            {selectedOS === 'windows' && (
              <ol style={{ paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '1rem', color: '#8B919E', lineHeight: '1.5' }}>
                <li>Run the downloaded <code>arceus-code-setup.exe</code> installer.</li>
                <li>If prompted by Windows SmartScreen, click <strong>More info</strong> and select <strong>Run anyway</strong>.</li>
                <li>On launch, select <strong>Sign in</strong> to link your Arceus subscription.</li>
                <li>Make sure you have Git installed on your system profile.</li>
              </ol>
            )}

            {selectedOS === 'macos' && (
              <ol style={{ paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '1rem', color: '#8B919E', lineHeight: '1.5' }}>
                <li>Double click the <code>.dmg</code> file to mount it.</li>
                <li>Drag the <strong>Arceus Code</strong> application icon into your <strong>Applications</strong> directory.</li>
                <li>Launch the app. Gatekeeper will verify the notarization signature.</li>
                <li>Accept accessibility permissions for terminal/command bindings.</li>
              </ol>
            )}

            {selectedOS === 'linux' && (
              <ol style={{ paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '1rem', color: '#8B919E', lineHeight: '1.5' }}>
                <li>Right click the <code>.AppImage</code> file, open <strong>Properties</strong>, and tick <strong>Allow executing file as program</strong>.</li>
                <li>Or run in terminal: <code>chmod +x arceus-code-x86_64.AppImage</code>.</li>
                <li>Execute the AppImage to start the application.</li>
                <li>Ensure FUSE libraries (e.g. <code>libfuse2</code>) are installed on your distribution.</li>
              </ol>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
