'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Mic, Search } from 'lucide-react';
import { apiRequest } from '../../utils/api';
import styles from './Launcher.module.css';

export default function LauncherPage() {
  const [command, setCommand] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [status, setStatus] = useState('Type or use the mic. Try: open code, interview, or remind me...');
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop?.();
      } catch {
        // Ignore browser speech cleanup failures.
      }
    };
  }, []);

  const getElectron = () => (typeof window !== 'undefined' ? (window as any).electron : null);

  const handleMicToggle = () => {
    if (isListening) {
      recognitionRef.current?.stop?.();
      setIsListening(false);
      setStatus('Mic paused');
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus('Voice is unavailable in this runtime. Type the command instead.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
      setStatus('Listening...');
    };
    recognition.onresult = (event: any) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }
      if (transcript.trim()) setCommand(transcript.trim());
    };
    recognition.onerror = (event: any) => {
      setStatus(`Voice error: ${event.error || 'could not listen'}`);
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      setStatus(command.trim() ? 'Ready to run command' : 'Type or use the mic. Try: open code, interview, or remind me...');
    };
    recognition.start();
  };

  const handleClose = () => {
    getElectron()?.hideLauncher?.();
    (window as any).document.activeElement?.blur();
  };

  const routeForCommand = (value: string) => {
    const normalized = value.toLowerCase();
    if (/\b(code|workspace|editor|repo|project)\b/.test(normalized)) return '/workspace';
    if (/\b(interview|resume|candidate)\b/.test(normalized)) return '/interview';
    if (/\b(pa|personal assistant|today|task|reminder|calendar|automation)\b/.test(normalized)) return '/pa';
    if (/\b(setting|settings|billing|usage)\b/.test(normalized)) return '/settings';
    if (/\b(hub|home|products)\b/.test(normalized)) return '/hub';
    return null;
  };

  const handleRunCommand = async () => {
    if (!command.trim()) return;
    const trimmed = command.trim();
    const route = routeForCommand(trimmed);

    if (route) {
      setStatus(`Opening ${route.replace('/', '') || 'home'}...`);
      getElectron()?.openRoute?.(route);
      setCommand('');
      return;
    }

    setStatus('Running command through NEXUS PA...');
    try {
      const result = await apiRequest('/api/v1/pa/command', {
        method: 'POST',
        body: JSON.stringify({ command: trimmed }),
      });
      setStatus(result?.summary || result?.message || result?.response || 'Command completed.');
      setCommand('');
      setTimeout(() => getElectron()?.hideLauncher?.(), 900);
    } catch (error: any) {
      setStatus(error?.message || 'Command failed.');
    }
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
