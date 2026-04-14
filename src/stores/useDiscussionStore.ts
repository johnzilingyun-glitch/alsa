import { create } from 'zustand';
import { AgentMessage, TradingPlanVersion, AnalystWeight, AgentDiscussion } from '../types';

interface DiscussionState {
  discussionMessages: AgentMessage[];
  controversialPoints: string[];
  tradingPlanHistory: TradingPlanVersion[];
  analystWeights: AnalystWeight[];
  currentRound: number;
  totalRounds: number;
  expectedValueOutcome: any | null;
  sensitivityMatrix: any[] | null;
  abortController: AbortController | null;

  setDiscussionMessages: (messages: AgentMessage[] | ((prev: AgentMessage[]) => AgentMessage[])) => void;
  setControversialPoints: (points: string[]) => void;
  setTradingPlanHistory: (history: TradingPlanVersion[] | ((prev: TradingPlanVersion[]) => TradingPlanVersion[])) => void;
  setAnalystWeights: (weights: AnalystWeight[]) => void;
  setDiscussionResults: (discussion: AgentDiscussion) => void;
  setRoundProgress: (current: number, total: number) => void;
  setAbortController: (controller: AbortController | null) => void;
  abortDiscussion: () => void;
  resetDiscussion: () => void;
}

const initialState = {
  discussionMessages: [] as AgentMessage[],
  controversialPoints: [] as string[],
  tradingPlanHistory: [] as TradingPlanVersion[],
  analystWeights: [] as AnalystWeight[],
  currentRound: 0,
  totalRounds: 0,
  expectedValueOutcome: null,
  sensitivityMatrix: null,
  abortController: null as AbortController | null,
};

export const useDiscussionStore = create<DiscussionState>((set, get) => ({
  ...initialState,

  setDiscussionMessages: (updater) => set((state) => ({
    discussionMessages: typeof updater === 'function' ? updater(state.discussionMessages) : updater,
  })),
  setControversialPoints: (controversialPoints) => set({ controversialPoints }),
  setTradingPlanHistory: (updater) => set((state) => ({
    tradingPlanHistory: typeof updater === 'function' ? updater(state.tradingPlanHistory) : updater,
  })),
  setAnalystWeights: (analystWeights) => set({ analystWeights }),
  setDiscussionResults: (discussion) => set({
    discussionMessages: discussion.messages,
    controversialPoints: discussion.controversialPoints || [],
    tradingPlanHistory: discussion.tradingPlanHistory || [],
    analystWeights: discussion.analystWeights || [],
    expectedValueOutcome: discussion.expectedValueOutcome || null,
    sensitivityMatrix: discussion.sensitivityMatrix || null,
  }),
  setRoundProgress: (currentRound, totalRounds) => set({ currentRound, totalRounds }),
  setAbortController: (abortController) => set({ abortController }),
  abortDiscussion: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ abortController: null });
    }
  },
  resetDiscussion: () => {
    const { abortController } = get();
    if (abortController) abortController.abort();
    set(initialState);
  },
}));
