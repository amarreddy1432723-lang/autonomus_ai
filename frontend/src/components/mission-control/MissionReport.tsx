import { Download, FileJson2, FileText, Printer } from 'lucide-react';
import styles from './MissionControlProduct.module.css';
import { formatDuration, missionStatusLabel } from './statusCopy';
import type {
  MissionControlChangeSet,
  MissionControlEvidence,
  MissionControlLock,
  MissionControlMetricsData,
  MissionControlMission,
  MissionControlRecovery,
  MissionControlTask,
  MissionControlVerificationStep,
  MissionControlWorker,
} from './types';

type MissionReportProps = {
  mission: MissionControlMission;
  workers: MissionControlWorker[];
  tasks: MissionControlTask[];
  locks: MissionControlLock[];
  metrics: MissionControlMetricsData;
  evidence: MissionControlEvidence[];
  recovery: MissionControlRecovery[];
  changeSet: MissionControlChangeSet;
  verification: MissionControlVerificationStep[];
};

function safeFileName(value: string) {
  const cleaned = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  return cleaned || 'arceus-mission';
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function buildReportModel({
  mission,
  workers,
  tasks,
  locks,
  metrics,
  evidence,
  recovery,
  changeSet,
  verification,
}: MissionReportProps) {
  const completedTasks = tasks.filter((task) => task.status === 'completed').length;
  const passedChecks = verification.filter((check) => check.status === 'passed').length;
  const failedChecks = verification.filter((check) => ['failed', 'blocked'].includes(check.status)).length;
  const additions = changeSet.files.reduce((sum, file) => sum + (file.additions || 0), 0);
  const deletions = changeSet.files.reduce((sum, file) => sum + (file.deletions || 0), 0);
  const riskyFiles = changeSet.files.filter((file) => file.reviewRequired || ['delete', 'rename'].includes(file.operation)).length;

  return {
    generatedAt: new Date().toISOString(),
    mission: {
      title: mission.title || 'Engineering Mission',
      repository: mission.repositoryName || 'Active repository',
      status: missionStatusLabel(mission.status),
      rawStatus: mission.status || 'unknown',
      duration: formatDuration(mission.durationSeconds),
      progress: Math.round(typeof mission.progress === 'number' ? (mission.progress <= 1 ? mission.progress * 100 : mission.progress) : 0),
    },
    summary: {
      tasks: metrics.taskCount ?? tasks.length,
      completedTasks: metrics.completedTasks ?? completedTasks,
      evidence: metrics.evidenceCount ?? evidence.length,
      filesChanged: changeSet.files.length,
      additions,
      deletions,
      verificationPassed: passedChecks,
      verificationFailed: failedChecks,
      rollbackAvailable: Boolean(changeSet.rollbackAvailable),
      recoveryReports: metrics.recoveryReports ?? recovery.length,
      activeReservations: metrics.activeReservations ?? locks.length,
    },
    workers: workers.map((worker) => ({
      role: worker.role,
      status: worker.status,
      task: worker.currentTaskTitle || worker.currentTaskKey || 'Waiting',
      confidence: worker.confidence,
    })),
    tasks: tasks.map((task) => ({
      key: task.taskKey,
      title: task.title,
      status: task.status,
      owner: task.ownerRole || 'Unassigned',
      evidenceCount: task.evidenceCount || 0,
      blockedReason: task.blockedReason || '',
    })),
    changes: {
      title: changeSet.title,
      reviewState: changeSet.reviewState,
      riskyFiles,
      files: changeSet.files.map((file) => ({
        path: file.path,
        operation: file.operation,
        additions: file.additions || 0,
        deletions: file.deletions || 0,
        risk: file.risk || 'low',
        reviewRequired: Boolean(file.reviewRequired),
        applied: Boolean(file.applied),
      })),
    },
    verification: verification.map((check) => ({
      label: check.label,
      status: check.status,
      command: check.command || '',
      summary: check.summary || '',
      durationMs: check.durationMs || null,
    })),
    evidence: evidence.slice(0, 25).map((item) => ({
      type: item.evidenceType || 'evidence',
      status: item.status,
      summary: item.summary,
      tool: item.tool || '',
      createdAt: item.createdAt || '',
    })),
    recovery: recovery.map((item) => ({
      taskKey: item.taskKey || '',
      status: item.status || '',
      stage: item.localStage || '',
      recommendedAction: item.recommendedAction || '',
    })),
  };
}

function toMarkdown(report: ReturnType<typeof buildReportModel>) {
  const lines = [
    `# Mission Report: ${report.mission.title}`,
    '',
    `- Repository: ${report.mission.repository}`,
    `- Status: ${report.mission.status}`,
    `- Duration: ${report.mission.duration}`,
    `- Progress: ${report.mission.progress}%`,
    '',
    '## Summary',
    '',
    `- Tasks: ${report.summary.completedTasks}/${report.summary.tasks} completed`,
    `- Evidence: ${report.summary.evidence}`,
    `- Files changed: ${report.summary.filesChanged}`,
    `- Line impact: +${report.summary.additions} / -${report.summary.deletions}`,
    `- Verification: ${report.summary.verificationPassed} passed, ${report.summary.verificationFailed} failed`,
    `- Rollback available: ${report.summary.rollbackAvailable ? 'Yes' : 'No'}`,
    `- Recovery reports: ${report.summary.recoveryReports}`,
    '',
    '## Workers',
    '',
    ...report.workers.map((worker) => `- ${worker.role}: ${worker.status} (${worker.task})`),
    '',
    '## Tasks',
    '',
    ...report.tasks.map((task) => `- ${task.key}: ${task.title} — ${task.status} — ${task.owner}`),
    '',
    '## Changed Files',
    '',
    ...(report.changes.files.length ? report.changes.files.map((file) => `- ${file.path}: ${file.operation}, +${file.additions}/-${file.deletions}, ${file.risk} risk${file.reviewRequired ? ', review required' : ''}`) : ['- No changes recorded.']),
    '',
    '## Verification',
    '',
    ...(report.verification.length ? report.verification.map((check) => `- ${check.label}: ${check.status}${check.summary ? ` — ${check.summary}` : ''}`) : ['- No verification checks recorded.']),
    '',
    '## Evidence',
    '',
    ...(report.evidence.length ? report.evidence.map((item) => `- ${item.summary} (${item.status})`) : ['- No evidence recorded.']),
  ];
  return `${lines.join('\n')}\n`;
}

function printReport(report: ReturnType<typeof buildReportModel>) {
  const markdown = toMarkdown(report);
  const html = `
    <!doctype html>
    <html>
      <head>
        <title>${escapeHtml(report.mission.title)} - Arceus Mission Report</title>
        <style>
          body { margin: 48px; color: #1b1b1f; font-family: Inter, Arial, sans-serif; }
          h1 { font-size: 28px; margin-bottom: 8px; }
          pre { white-space: pre-wrap; font: 13px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; }
        </style>
      </head>
      <body>
        <h1>Arceus Code Mission Report</h1>
        <pre>${escapeHtml(markdown)}</pre>
      </body>
    </html>
  `;
  const popup = window.open('', '_blank', 'noopener,noreferrer,width=960,height=1200');
  if (!popup) return;
  popup.document.write(html);
  popup.document.close();
  popup.focus();
  popup.print();
}

export function MissionReport(props: MissionReportProps) {
  const report = buildReportModel(props);
  const baseName = safeFileName(report.mission.title);

  return (
    <section className={styles.reportPanel} aria-label="Mission report">
      <header>
        <div>
          <span className={styles.reportEyebrow}>Mission Report</span>
          <h3>{report.mission.title}</h3>
          <p>
            {report.mission.status} · {report.mission.duration} · {report.summary.completedTasks}/{report.summary.tasks} tasks completed
          </p>
        </div>
        <span className={styles.statusPill} data-state={props.mission.status}>
          {report.summary.rollbackAvailable ? 'Rollback available' : 'Rollback not recorded'}
        </span>
      </header>
      <div className={styles.reportStats}>
        <span><b>{report.summary.evidence}</b> Evidence</span>
        <span><b>{report.summary.filesChanged}</b> Files</span>
        <span data-tone="good"><b>{report.summary.verificationPassed}</b> Checks passed</span>
        <span data-tone={report.summary.verificationFailed ? 'warn' : 'good'}><b>{report.summary.verificationFailed}</b> Checks failed</span>
      </div>
      <div className={styles.reportActions}>
        <button
          type="button"
          data-primary="true"
          onClick={() => downloadText(`${baseName}-mission-report.md`, toMarkdown(report), 'text/markdown;charset=utf-8')}
        >
          <FileText size={14} /> Markdown
        </button>
        <button
          type="button"
          onClick={() => downloadText(`${baseName}-mission-report.json`, JSON.stringify(report, null, 2), 'application/json;charset=utf-8')}
        >
          <FileJson2 size={14} /> JSON
        </button>
        <button type="button" onClick={() => printReport(report)}>
          <Printer size={14} /> PDF
        </button>
        <button
          type="button"
          onClick={() => downloadText(`${baseName}-evidence-summary.json`, JSON.stringify({ mission: report.mission, evidence: report.evidence }, null, 2), 'application/json;charset=utf-8')}
        >
          <Download size={14} /> Evidence
        </button>
      </div>
    </section>
  );
}
