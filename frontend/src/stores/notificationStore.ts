import { create } from 'zustand';

export type NotificationKind =
  | 'info'
  | 'success'
  | 'warning'
  | 'error'
  | 'approval_required'
  | 'mission_completed'
  | 'deployment_failed'
  | 'billing_issue'
  | 'update_available';

export interface ArceusNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  detail?: string;
  resourceHref?: string;
  read: boolean;
  createdAt: string;
}

interface NotificationStore {
  notifications: ArceusNotification[];
  push: (notification: Omit<ArceusNotification, 'id' | 'read' | 'createdAt'>) => string;
  markRead: (id: string) => void;
  clear: () => void;
}

export const useNotificationStore = create<NotificationStore>((set) => ({
  notifications: [],
  push: (notification) => {
    const id = crypto.randomUUID();
    set((state) => ({
      notifications: [
        {
          ...notification,
          id,
          read: false,
          createdAt: new Date().toISOString(),
        },
        ...state.notifications,
      ].slice(0, 100),
    }));
    return id;
  },
  markRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((item) => (item.id === id ? { ...item, read: true } : item)),
    })),
  clear: () => set({ notifications: [] }),
}));

