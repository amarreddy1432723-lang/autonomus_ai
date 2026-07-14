'use client';

import { AlertTriangle, Camera, CheckCircle2, ExternalLink, Monitor, RefreshCw, Wrench } from 'lucide-react';
import { useState } from 'react';
import styles from './Workspace.module.css';
import type { PreviewCheck, PreviewLogs } from './ActivityPanel';

type Props = {
  previewUrl: string;
  previewChecks: PreviewCheck[];
  previewLogs: PreviewLogs | null;
  canCheckPreview: boolean;
  canFixPreview: boolean;
  canStartPreview: boolean;
  onPreviewUrlChange: (value: string) => void;
  onCheckPreview: () => void;
  onFixPreview: (instruction?: string) => void;
  onStartPreview: () => void;
  onStopPreview: () => void;
  onLoadPreviewLogs: () => void;
};

function latestIssue(check?: PreviewCheck) {
  if (!check) return '';
  if (check.issues?.length) return check.issues[0];
  if (check.blank_page) return 'Blank page detected';
  if (check.playwright_error) return check.playwright_error;
  return check.status === 'passed' ? 'No visible issue detected' : 'Preview failed';
}

function screenshotUrl(check: PreviewCheck) {
  if (check.screenshot_base64) return `data:image/png;base64,${check.screenshot_base64}`;
  return check.screenshot_url || check.artifacts?.find((item) => item.kind === 'screenshot')?.url || '';
}

function consoleText(error: NonNullable<PreviewCheck['console_errors']>[number]) {
  if (typeof error === 'string') return error;
  const location = [error.url, error.line ? `:${error.line}` : '', error.column ? `:${error.column}` : ''].filter(Boolean).join('');
  const args = error.args?.length ? `\nargs: ${error.args.join(', ')}` : '';
  return `${error.text || 'Console error'}${location ? `\n${location}` : ''}${args}`;
}

function networkFailureText(failure: NonNullable<PreviewCheck['network_failures']>[number]) {
  return `${failure.method || ''} ${failure.url || 'unknown'} ${failure.error || (failure.failure ? JSON.stringify(failure.failure) : '')}`.trim();
}

function buildAutoFixPrompt(check?: PreviewCheck) {
  if (!check) return 'Prepare the smallest safe code change that fixes the latest preview failure.';
  const consoleErrors = (check.console_errors || []).map(consoleText).join('\n');
  const networkFailures = (check.network_failures || []).map(networkFailureText).join('\n');
  return [
    'Prepare the smallest safe code change that fixes this preview verification failure.',
    `Preview URL: ${check.url || 'unknown'}`,
    `Status: ${check.status || 'unknown'}${check.status_code ? ` HTTP ${check.status_code}` : ''}`,
    `Blank page: ${check.blank_page ? 'yes' : 'no'}`,
    `Issues: ${(check.issues || []).join(', ') || 'none listed'}`,
    consoleErrors ? `Console errors:\n${consoleErrors}` : 'Console errors: none captured',
    networkFailures ? `Network failures:\n${networkFailures}` : 'Network failures: none captured',
    check.first_contentful_paint_ms ? `First contentful paint: ${Math.round(check.first_contentful_paint_ms)}ms` : '',
    'Use the screenshot and browser evidence first. Do not rewrite unrelated files.',
  ].filter(Boolean).join('\n');
}

export default function PreviewPanel({
  previewUrl,
  previewChecks,
  previewLogs,
  canCheckPreview,
  canFixPreview,
  canStartPreview,
  onPreviewUrlChange,
  onCheckPreview,
  onFixPreview,
  onStartPreview,
  onStopPreview,
  onLoadPreviewLogs,
}: Props) {
  const latest = previewChecks[previewChecks.length - 1];
  const failed = latest && latest.status !== 'passed';
  const screenshots = previewChecks.filter((check) => check.screenshot_path || screenshotUrl(check)).slice(-5).reverse();
  const [selectedShot, setSelectedShot] = useState<string>('');

  return (
    <div className={styles.previewPanelShell}>
      <div className={styles.previewHero}>
        <div>
          <span><Monitor size={13} /> Preview</span>
          <strong>{latest?.status || 'not checked'}</strong>
        </div>
        {failed ? (
          <em data-status="failed"><AlertTriangle size={13} /> {latestIssue(latest)}</em>
        ) : (
          <em data-status="passed"><CheckCircle2 size={13} /> {latest ? 'Verified' : 'Ready'}</em>
        )}
      </div>

      <div className={styles.previewInputRow}>
        <input
          className={styles.previewInput}
          value={previewUrl}
          onChange={(event) => onPreviewUrlChange(event.target.value)}
          placeholder="https://your-preview-url.app"
        />
        <button className={styles.commandButton} type="button" onClick={onCheckPreview} disabled={!canCheckPreview}>
          <RefreshCw size={13} /> Re-verify
        </button>
      </div>

      <div className={styles.previewButtonRow}>
        <button className={styles.commandButton} type="button" onClick={onStartPreview} disabled={!canStartPreview}>Start live</button>
        <button className={styles.commandButton} type="button" onClick={onStopPreview} disabled={!canStartPreview}>Stop</button>
        <button className={styles.commandButton} type="button" onClick={onLoadPreviewLogs} disabled={!canStartPreview}>Logs</button>
      </div>

      <button className={styles.fullWidthButton} type="button" onClick={() => onFixPreview(buildAutoFixPrompt(latest))} disabled={!canFixPreview}>
        <Wrench size={13} /> Auto-fix from evidence
      </button>

      {previewUrl.trim() ? (
        <div className={styles.previewFrameWrap}>
          {failed && <div className={styles.previewErrorBadge}>{latestIssue(latest)}</div>}
          <iframe className={styles.previewFrame} src={previewUrl.trim()} title="Workspace preview" sandbox="allow-scripts allow-same-origin allow-forms" />
          <a href={previewUrl.trim()} target="_blank" rel="noreferrer" className={styles.previewOpenLink}>
            <ExternalLink size={12} /> Open
          </a>
        </div>
      ) : (
        <div className={styles.previewEmpty}>Start live preview or paste a URL to verify the app visually.</div>
      )}

      <div className={styles.previewScreenshotStrip}>
        <div className={styles.previewSectionTitle}>
          <span><Camera size={13} /> Last screenshots</span>
          <em>{screenshots.length}</em>
        </div>
        {screenshots.length ? (
          <div className={styles.previewShotList}>
            {screenshots.map((check, index) => (
              <button
                type="button"
                className={check.status === 'passed' ? styles.previewShotPass : styles.previewShotFail}
                key={`${check.screenshot_path || check.checked_at || check.url}-${index}`}
                onClick={() => setSelectedShot(screenshotUrl(check))}
                disabled={!screenshotUrl(check)}
              >
                {screenshotUrl(check) && <img src={screenshotUrl(check)} alt={`Preview screenshot ${check.status}`} />}
                <strong>{check.status}</strong>
                <span>{check.checked_at ? new Date(check.checked_at).toLocaleTimeString() : 'recent'}</span>
                <em>{check.screenshot_path?.split(/[\\/]/).pop() || (check.screenshot_base64 ? 'captured screenshot' : '')}</em>
              </button>
            ))}
          </div>
        ) : (
          <div className={styles.previewEmptySmall}>No screenshots captured yet.</div>
        )}
      </div>

      {selectedShot && (
        <button className={styles.previewShotViewer} type="button" onClick={() => setSelectedShot('')} title="Close screenshot">
          <img src={selectedShot} alt="Preview verification screenshot" />
        </button>
      )}

      {previewChecks.length > 0 && (
        <div className={styles.previewEvidence}>
          {previewChecks.slice(-5).reverse().map((check, index) => (
            <div className={check.status === 'passed' ? styles.previewEvidencePass : styles.previewEvidenceFail} key={`${check.url}-${check.checked_at || index}`}>
              <div>
                <strong>{check.status || 'unknown'} {check.status_code ? `HTTP ${check.status_code}` : ''}</strong>
                <span>{check.title || check.url}</span>
              </div>
              <div className={styles.previewEvidenceMeta}>
                <span>{check.browser || 'http'}</span>
                <span>{check.console_errors?.length || 0} console</span>
                <span>{check.page_errors?.length || 0} page</span>
                <span>{check.network_failures?.length || 0} network</span>
                {check.blank_page && <span>blank</span>}
                {check.first_contentful_paint_ms && <span>FCP {Math.round(check.first_contentful_paint_ms)}ms</span>}
              </div>
              <div className={styles.previewEvidenceMeta}>
                <span>{check.status === 'passed' ? 'Passed' : 'Needs attention'}</span>
                {!!check.console_errors?.length && <span>{check.console_errors.length} console error(s)</span>}
                {check.blank_page && <span>Blank page detected</span>}
              </div>
              {check.issues?.length ? <em>{check.issues.join(', ')}</em> : <em>No issue markers</em>}
              {!!check.console_errors?.length && (
                <details>
                  <summary>{check.console_errors.length} console error(s)</summary>
                  <pre>{check.console_errors.map(consoleText).join('\n\n')}</pre>
                </details>
              )}
              {!!check.network_failures?.length && (
                <details>
                  <summary>{check.network_failures.length} network failure(s)</summary>
                  <pre>{check.network_failures.map(networkFailureText).join('\n')}</pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}

      {previewLogs?.logs && (
        <div className={styles.previewLogs}>
          <div className={styles.meta}>
            {previewLogs.status || 'preview'} {previewLogs.issues?.length ? `- ${previewLogs.issues.join(', ')}` : ''}
          </div>
          {previewLogs.excerpts?.length ? (
            <div className={styles.previewExcerpts}>
              {previewLogs.excerpts.map((line, index) => <span key={`${line}-${index}`}>{line}</span>)}
            </div>
          ) : null}
          <pre>{previewLogs.logs}</pre>
        </div>
      )}
    </div>
  );
}
