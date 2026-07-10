'use client';

import React, { useState, useEffect } from 'react';
import { Mic, Search, X, Calendar, Play } from 'lucide-react';
import styles from './Launcher.module.css';

export default function LauncherPage() {
  const [command, setCommand] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [status, setStatus] = useState('Type or click mic to dictate command...');

  const handleMicToggle = () => {
    setIsListening(!isListening);
    if (!isListening) {
      setStatus('Listening to voice...');
      // Simulate speech-to-text response after 3 seconds
      setTimeout(() => {
        setCommand('Schedule team review today at 3pm');
        setIsListening(false);
        setStatus('Ready to run command');
      }, 3000);
    } else {
      setStatus('Mic paused');
    }
  };

  const handleClose = () => {
    if (typeof window !== 'undefined' && (window as any).electron) {
      // Blur focuses back, which hides the launcher automatically based on the main process listeners
      (window as any).document.activeElement?.blur();
    }
  };

  const handleRunCommand = () => {
    if (!command.trim()) return;
    setStatus(`Executing: "${command}"...`);
    setTimeout(() => {
      setStatus('Action completed successfully.');
      setCommand('');
    }, 1500);
  };

  return (
    <div className={styles.launcher}>
      <div className={styles.searchBar}>
        <Search className={styles.icon} size={20} />
        <input
          type="text"
          className={styles.input}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleRunCommand();
            if (e.key === 'Escape') handleClose();
          }}
          placeholder="What would you like me to do?"
          autoFocus
        />
        <button className={`${styles.micButton} ${isListening ? styles.activeMic : ''}`} onClick={handleMicToggle}>
          <Mic size={18} />
        </button>
      </div>

      <div className={styles.statusFooter}>
        <span className={styles.statusText}>{status}</span>
        {isListening && (
          <div className={styles.waveform}>
            <div className={styles.bar}></div>
            <div className={styles.bar}></div>
            <div className={styles.bar}></div>
            <div className={styles.bar}></div>
            <div className={styles.bar}></div>
          </div>
        )}
      </div>
    </div>
  );
}
