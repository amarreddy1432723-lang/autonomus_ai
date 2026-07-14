'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Download, ArrowRight, Shield, Cpu, Layers, CheckCircle2, ChevronRight, Terminal, FileCode, Check } from 'lucide-react';

export default function ArceusCodeProductPage() {
  const [detectedOS, setDetectedOS] = useState<'windows' | 'macos' | 'linux' | 'unknown'>('unknown');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const ua = window.navigator.userAgent.toLowerCase();
    if (ua.includes('win')) {
      setDetectedOS('windows');
    } else if (ua.includes('mac')) {
      setDetectedOS('macos');
    } else if (ua.includes('linux')) {
      setDetectedOS('linux');
    }
  }, []);

  const downloadText = {
    windows: 'Download for Windows (x64)',
    macos: 'Download for macOS (Universal)',
    linux: 'Download for Linux (AppImage)',
    unknown: 'Download Arceus Code',
  };

  const downloadHref = {
    windows: '/download?os=windows',
    macos: '/download?os=macos',
    linux: '/download?os=linux',
    unknown: '/download',
  };

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#08090E',
      color: '#F0F2F5',
      fontFamily: 'Inter, system-ui, sans-serif',
      padding: '4rem 2rem',
      overflowY: 'auto'
    }}>
      {/* Top Navbar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        maxWidth: '1200px',
        margin: '0 auto 4rem auto',
        padding: '0 1rem'
      }}>
        <Link href="/" style={{
          fontSize: '1.5rem',
          fontWeight: '800',
          color: '#4F8EF7',
          textDecoration: 'none',
          letterSpacing: '-1px'
        }}>
          ARCEUS.AI
        </Link>
        <div style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
          <Link href="/products" style={{ color: '#8B919E', textDecoration: 'none' }}>Products</Link>
          <Link href="/pricing" style={{ color: '#8B919E', textDecoration: 'none' }}>Pricing</Link>
          <Link href="/docs" style={{ color: '#8B919E', textDecoration: 'none' }}>Docs</Link>
          <Link href="/dashboard" style={{
            background: 'rgba(79, 142, 247, 0.1)',
            border: '1px solid #4F8EF7',
            padding: '0.5rem 1.2rem',
            borderRadius: '6px',
            color: '#4F8EF7',
            textDecoration: 'none',
            fontWeight: '600'
          }}>
            Dashboard
          </Link>
        </div>
      </div>

      {/* Hero Section */}
      <div style={{
        maxWidth: '1000px',
        margin: '0 auto 6rem auto',
        textAlign: 'center',
        padding: '0 1rem'
      }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          backgroundColor: 'rgba(79, 142, 247, 0.1)',
          color: '#4F8EF7',
          padding: '0.4rem 1rem',
          borderRadius: '99px',
          fontSize: '0.875rem',
          fontWeight: '600',
          marginBottom: '2rem'
        }}>
          <span>Introducing Arceus Code 1.0</span>
          <ChevronRight size={14} />
        </div>
        <h1 style={{
          fontSize: '3.5rem',
          fontWeight: '900',
          lineHeight: '1.15',
          letterSpacing: '-2px',
          marginBottom: '1.5rem',
          background: 'linear-gradient(to right, #F0F2F5, #4F8EF7)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent'
        }}>
          Your AI engineering partner that plans, decides, and executes.
        </h1>
        <p style={{
          fontSize: '1.25rem',
          color: '#8B919E',
          maxWidth: '750px',
          margin: '0 auto 3rem auto',
          lineHeight: '1.6'
        }}>
          Arceus Code is a next-generation desktop coding workspace that maps project dependencies, detects missing requirements, writes plans, modifies code safely, and runs validation smoke tests.
        </p>

        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '1rem',
          flexWrap: 'wrap'
        }}>
          <Link href={downloadHref[detectedOS]} style={{
            background: '#4F8EF7',
            color: '#08090E',
            padding: '1rem 2.2rem',
            borderRadius: '8px',
            fontSize: '1.1rem',
            fontWeight: '800',
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.75rem',
            boxShadow: '0 4px 20px rgba(79, 142, 247, 0.4)'
          }}>
            <Download size={20} />
            {downloadText[detectedOS]}
          </Link>
          <Link href="/docs" style={{
            background: '#161B27',
            color: '#F0F2F5',
            border: '1px solid #1E2535',
            padding: '1rem 2.2rem',
            borderRadius: '8px',
            fontSize: '1.1rem',
            fontWeight: '700',
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            View Documentation
            <ArrowRight size={18} />
          </Link>
        </div>
      </div>

      {/* Capabilities Section */}
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto 6rem auto',
        padding: '0 1rem'
      }}>
        <h2 style={{
          fontSize: '2rem',
          fontWeight: '800',
          textAlign: 'center',
          marginBottom: '3rem',
          letterSpacing: '-1px'
        }}>
          Built for Complex Software Development Tasks
        </h2>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '2rem'
        }}>
          {[
            {
              icon: <Layers size={24} color="#4F8EF7" />,
              title: 'Analyze Architecture & Codebases',
              desc: 'Arceus scans and indexes files, functions, dependency trees, and package references to build a persistent project brain.'
            },
            {
              icon: <Terminal size={24} color="#00D084" />,
              title: 'Isolated Command Execution',
              desc: 'Run compile checks, local web servers, and unit tests safely inside hardened Docker sandboxes.'
            },
            {
              icon: <FileCode size={24} color="#9B5DE5" />,
              title: 'Precision Hunk Patching',
              desc: 'Review, accept, or reject individual diff blocks generated by the agent. No random file overwrites.'
            },
            {
              icon: <Shield size={24} color="#F5A623" />,
              title: 'Abuse & Permission Guard',
              desc: 'Arceus requests user approval before making file changes, installing packages, or accessing external repositories.'
            },
            {
              icon: <Cpu size={24} color="#4F8EF7" />,
              title: 'What-Should-I-Do-Next System',
              desc: 'The Project Navigator panel maps out recommended developer actions, detailed why logs, and manual/automated routes.'
            },
            {
              icon: <CheckCircle2 size={24} color="#00D084" />,
              title: 'Playwright Preview Loop',
              desc: 'Automatic screenshots, FCP metric analysis, console log parsing, and blank-page detection verify UI builds.'
            }
          ].map((cap, i) => (
            <div key={i} style={{
              background: '#0F1117',
              border: '1px solid #1E2535',
              borderRadius: '12px',
              padding: '2rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem'
            }}>
              <div style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid #1E2535',
                width: '48px',
                height: '48px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                {cap.icon}
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: '700' }}>{cap.title}</h3>
              <p style={{ color: '#8B919E', lineHeight: '1.6', fontSize: '0.95rem' }}>{cap.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* System Requirements Section */}
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '0 1rem'
      }}>
        <h2 style={{
          fontSize: '2rem',
          fontWeight: '800',
          textAlign: 'center',
          marginBottom: '3rem',
          letterSpacing: '-1px'
        }}>
          System Requirements
        </h2>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '2rem',
          marginBottom: '4rem'
        }}>
          {[
            {
              os: 'Windows',
              requirements: [
                'Windows 10 or later (64-bit)',
                'Intel Core i5 / AMD Ryzen 5 or higher',
                'Minimum 8 GB RAM (16 GB Recommended)',
                '2 GB free storage space',
                'Git version 2.30+ installed',
                'Docker Desktop (Optional, for container sandbox)'
              ]
            },
            {
              os: 'macOS',
              requirements: [
                'macOS 12.0 (Monterey) or later',
                'Apple Silicon (M1/M2/M3) or Intel Core',
                'Minimum 8 GB Unified Memory',
                '3 GB free storage space',
                'Xcode Command Line Tools installed',
                'Docker Desktop (Optional, for container sandbox)'
              ]
            },
            {
              os: 'Linux',
              requirements: [
                'Ubuntu 20.04+, Debian 11+, Fedora 36+',
                'x86_64 or ARM64 processor',
                'Minimum 8 GB RAM',
                '2 GB free storage space',
                'FUSE dependencies (for AppImage runtimes)',
                'Docker engine configured (for sandbox execution)'
              ]
            }
          ].map((sys, idx) => (
            <div key={idx} style={{
              background: '#0F1117',
              border: '1px solid #1E2535',
              borderRadius: '12px',
              padding: '2rem'
            }}>
              <h3 style={{
                fontSize: '1.4rem',
                fontWeight: '800',
                color: '#4F8EF7',
                marginBottom: '1.5rem',
                borderBottom: '1px solid #1E2535',
                paddingBottom: '0.75rem'
              }}>
                {sys.os}
              </h3>
              <ul style={{
                listStyle: 'none',
                padding: '0',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.8rem'
              }}>
                {sys.requirements.map((req, rIdx) => (
                  <li key={rIdx} style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.5rem',
                    color: '#8B919E',
                    fontSize: '0.9rem',
                    lineHeight: '1.4'
                  }}>
                    <Check size={14} color="#00D084" style={{ marginTop: '0.2rem', flexShrink: 0 }} />
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
