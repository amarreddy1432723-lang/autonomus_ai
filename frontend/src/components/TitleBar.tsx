'use client';

import React, { useEffect, useState } from 'react';
import styles from './TitleBar.module.css';

export default function TitleBar() {
  const [isElectron, setIsElectron] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).electron) {
      setIsElectron(true);
    }
  }, []);

  if (!isElectron) return null;

  const handleMinimize = () => {
    (window as any).electron.minimize();
  };

  const handleMaximize = () => {
    (window as any).electron.maximize();
  };

  const handleClose = () => {
    (window as any).electron.close();
  };

  return (
    <div className={styles.titleBar}>
      <div className={styles.titleDragRegion}>
        <img className={styles.logo} src="/arceus-logo.svg" alt="" aria-hidden="true" />
        <span className={styles.titleText}>Arceus Code</span>
      </div>
      <div className={styles.windowControls}>
        <button className={styles.controlButton} onClick={handleMinimize} aria-label="Minimize">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="2" y="5.5" width="8" height="1" fill="currentColor" />
          </svg>
        </button>
        <button className={styles.controlButton} onClick={handleMaximize} aria-label="Maximize">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="2.5" y="2.5" width="7" height="7" stroke="currentColor" strokeWidth="1" fill="none" />
          </svg>
        </button>
        <button className={`${styles.controlButton} ${styles.closeButton}`} onClick={handleClose} aria-label="Close">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 2.5L9.5 9.5M9.5 2.5L2.5 9.5" stroke="currentColor" strokeWidth="1" />
          </svg>
        </button>
      </div>
    </div>
  );
}
