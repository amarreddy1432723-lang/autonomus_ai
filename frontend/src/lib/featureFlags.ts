export type FeatureFlagKey =
  | 'multiAgentMissionView'
  | 'desktopCodeShell'
  | 'offlineLocalMode'
  | 'uiPreviews'
  | 'civilizationRoutes'
  | 'adminReleaseGate';

export type FeatureFlag = {
  key: FeatureFlagKey;
  enabled: boolean;
  owner: string;
  description: string;
  rolloutPercentage: number;
  expiresAt?: string;
};

const env = {
  multiAgentMissionView: process.env.NEXT_PUBLIC_ENABLE_MISSION_CONTROL !== 'false',
  desktopCodeShell: process.env.NEXT_PUBLIC_ENABLE_DESKTOP_CODE_SHELL !== 'false',
  offlineLocalMode: process.env.NEXT_PUBLIC_ENABLE_OFFLINE_LOCAL_MODE !== 'false',
  uiPreviews: process.env.NEXT_PUBLIC_ENABLE_UI_PREVIEWS === 'true',
  civilizationRoutes: process.env.NEXT_PUBLIC_ENABLE_CIVILIZATION_UI === 'true',
  adminReleaseGate: process.env.NEXT_PUBLIC_ENABLE_ADMIN_RELEASE_GATE !== 'false',
};

export const featureFlags: Record<FeatureFlagKey, FeatureFlag> = {
  multiAgentMissionView: {
    key: 'multiAgentMissionView',
    enabled: env.multiAgentMissionView,
    owner: 'Frontend Platform',
    description: 'Enables the mission-control style AI organization workspace.',
    rolloutPercentage: 100,
  },
  desktopCodeShell: {
    key: 'desktopCodeShell',
    enabled: env.desktopCodeShell,
    owner: 'Desktop Platform',
    description: 'Uses the Arceus Code-only shell inside Electron.',
    rolloutPercentage: 100,
  },
  offlineLocalMode: {
    key: 'offlineLocalMode',
    enabled: env.offlineLocalMode,
    owner: 'Desktop Platform',
    description: 'Keeps local files, editor, and terminal usable when cloud APIs are offline.',
    rolloutPercentage: 100,
  },
  uiPreviews: {
    key: 'uiPreviews',
    enabled: env.uiPreviews,
    owner: 'Design Systems',
    description: 'Enables internal visual storyboard routes.',
    rolloutPercentage: env.uiPreviews ? 100 : 0,
    expiresAt: '2026-09-30',
  },
  civilizationRoutes: {
    key: 'civilizationRoutes',
    enabled: env.civilizationRoutes,
    owner: 'AIOS Platform',
    description: 'Shows experimental civilization-layer UI surfaces.',
    rolloutPercentage: env.civilizationRoutes ? 100 : 0,
  },
  adminReleaseGate: {
    key: 'adminReleaseGate',
    enabled: env.adminReleaseGate,
    owner: 'SRE',
    description: 'Shows release readiness and observability checks in admin.',
    rolloutPercentage: 100,
  },
};

export function isFeatureEnabled(key: FeatureFlagKey) {
  return featureFlags[key]?.enabled ?? false;
}

