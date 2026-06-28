import { create } from 'zustand';

export interface User {
  id: string;
  email: string;
}

export interface AgentEvent {
  id: string;
  agent: string;
  activity: string;
  timestamp: string;
  status?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  thoughts?: string[];
  sources?: string[];
}

interface AppState {
  currentUser: User | null;
  sidebarCollapsed: boolean;
  activeGoalContext: { id: string; title: string } | null;
  agentActivityFeed: AgentEvent[];
  pendingApprovalCount: number;
  commandPaletteOpen: boolean;
  setCurrentUser: (user: User | null) => void;
  toggleSidebar: () => void;
  setActiveGoalContext: (goal: { id: string; title: string } | null) => void;
  addAgentEvent: (event: AgentEvent) => void;
  setPendingApprovalCount: (count: number) => void;
  toggleCommandPalette: () => void;
  setCommandPalette: (open: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentUser: { id: '00000000-0000-0000-0000-000000000000', email: 'user@example.com' },
  sidebarCollapsed: false,
  activeGoalContext: null,
  agentActivityFeed: [
    { id: '1', agent: 'Research Agent', activity: 'Completed SaaS pricing analysis', timestamp: '9:04 AM', status: 'done' },
    { id: '2', agent: 'Coding Agent', activity: 'Started Auth JWT middleware', timestamp: '9:12 AM', status: 'running' },
    { id: '3', agent: 'Memory Agent', activity: 'Stored 4 new memories', timestamp: '9:12 AM', status: 'done' },
    { id: '4', agent: 'Scheduler', activity: 'Scheduled morning standup reminder', timestamp: '9:00 AM', status: 'done' }
  ],
  pendingApprovalCount: 2,
  commandPaletteOpen: false,
  setCurrentUser: (user) => set({ currentUser: user }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setActiveGoalContext: (goal) => set({ activeGoalContext: goal }),
  addAgentEvent: (event) => set((state) => ({ agentActivityFeed: [event, ...state.agentActivityFeed].slice(0, 50) })),
  setPendingApprovalCount: (count) => set({ pendingApprovalCount: count }),
  toggleCommandPalette: () => set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),
  setCommandPalette: (open) => set({ commandPaletteOpen: open })
}));

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  streamingThoughts: string[];
  addMessage: (msg: ChatMessage) => void;
  setMessages: (msgs: ChatMessage[]) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setStreamingContent: (content: string) => void;
  setStreamingThoughts: (thoughts: string[]) => void;
  clearChat: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [
    {
      id: 'm1',
      role: 'assistant',
      content: `I've completed the cloud pricing research. Here's what I found:

**AWS vs GCP vs Azure for Early-Stage SaaS**

| Provider | Free Tier | Est. Monthly | Best For |
|---|---|---|---|
| AWS | 12 months | $45-120 | Scale |
| GCP | $300 credit | $35-95 | ML/Data |
| Render | Generous | $25-60 | Startups |

💡 **Recommendation**: Start with Render or Railway for MVP. Migrate to AWS when you hit $10K MRR.

📚 Sources: [AWS Pricing], [GCP Calc], [Render Docs]`,
      timestamp: '9:04 AM',
      thoughts: ['Brain: Classified as general_chat', 'Memory: Found preference cloud=AWS']
    }
  ],
  isStreaming: false,
  streamingContent: '',
  streamingThoughts: [],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingContent: (content) => set({ streamingContent: content }),
  setStreamingThoughts: (thoughts) => set({ streamingThoughts: thoughts }),
  clearChat: () => set({ messages: [], streamingContent: '', streamingThoughts: [] })
}));
