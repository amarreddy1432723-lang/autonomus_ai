import type { ArceusClientSurface } from '@/types/arceus-frontend';
import { routeBoundaries } from './frontendBoundaries';

export const frontendArchitecture = {
  productSurfaces: {
    hub: {
      surface: 'web' satisfies ArceusClientSurface,
      purpose: 'Product discovery, onboarding, account management, downloads, pricing.',
      ownsRoutes: ['/', '/products', '/pricing', '/download', '/docs'],
    },
    web: {
      surface: 'web' satisfies ArceusClientSurface,
      purpose: 'Browser-based AI engineering workspace and cloud mission monitoring.',
      ownsRoutes: ['/workspace', '/mission-control', '/settings'],
    },
    desktop: {
      surface: 'desktop' satisfies ArceusClientSurface,
      purpose: 'Local development environment with trusted folders, terminal, Git, and editor capabilities.',
      ownsRoutes: routeBoundaries.filter((route) => route.desktopAllowed).map((route) => route.prefix),
    },
    admin: {
      surface: 'admin' satisfies ArceusClientSurface,
      purpose: 'Operations, release readiness, billing health, usage, audit, and governance.',
      ownsRoutes: ['/admin'],
    },
  },
  stateLayers: {
    serverState: 'TanStack Query',
    globalUiState: 'Zustand',
    formState: 'React Hook Form + Zod',
    urlState: 'Next.js router/search params',
    editorState: 'Monaco models',
    desktopState: 'Electron IPC-backed store',
    sessionState: 'Clerk and desktop auth bridge',
  },
  performanceBudgets: {
    marketingLcpMs: 2500,
    dashboardInteractionMs: 100,
    workspaceInitialShellMs: 2000,
    routeTransitionMs: 300,
    chatStreamUiOverheadMs: 100,
    editorInputLatencyMs: 50,
  },
  mvpScope: [
    'authentication',
    'workspace_selection',
    'repository_opening',
    'ai_chat',
    'mission_creation',
    'basic_agent_progress',
    'monaco_editor',
    'terminal',
    'diff_review',
    'model_configuration',
    'settings',
    'desktop_download_and_update_flow',
  ],
  delayedScope: [
    'marketplace',
    'federation_ui',
    'civilization_dashboards',
    'advanced_visual_workflow_builder',
    'mobile_client',
    'enterprise_customization',
    'complex_offline_synchronization',
  ],
} as const;

