export type Snapshot = {
  at: string;
  nav: string;
  nav_eur: string;
  cash: string;
  invested_cost: string;
  realized: string;
  unrealized: string;
  roi: string;
  stranded: string[];
  valuation: string;
};
export type Position = {
  market_id: string;
  outcome: string;
  quantity: string;
  cost: string;
};
export type Decision = {
  at: string;
  action: string;
  market_id: string;
  outcome: string | null;
  reasoning: string;
  sources: string[];
  confidence: string;
  estimated_probability: string;
  verified_edge: string;
  exit_plan: string;
  risk_factors: string[];
  rejection: string;
  decision_status?: string;
};
export type Order = {
  id: string;
  at: string;
  market_id: string;
  outcome: string;
  action: string;
  status: string;
  reason: string;
  execution: {
    fills: { price: string; quantity: string; fee: string }[];
  } | null;
};
export type Agent = {
  id: string;
  name: string;
  initial_eur: string;
  dynamic: boolean;
  prompt: string;
  risk: Record<string, string | number | boolean>;
  runtime?: { status: string; at: string; reason: string };
  wallet: {
    initial: string;
    cash: string;
    realized: string;
    positions: Record<string, Position>;
  };
  memory: {
    summary?: string;
    exit_plan?: string;
    calls?: number;
    last_call?: string;
    paused_until?: string;
  };
  stats: {
    max_drawdown: string;
    trades: number;
    wins: number;
    closed: number;
    categories: Record<string, string>;
    llm_usage?: {requests: number; prompt_tokens: number; completion_tokens: number; model?: string; metering_started_at?: string};
  };
  snapshot?: Snapshot;
  decisions: Decision[];
  orders: Order[];
};
export type Book = {
  observed_at: string;
  bids: { price: string; size: string }[];
  asks: { price: string; size: string }[];
  minimum: string;
  tick: string;
  fee_rate: string;
  asset_id: string;
};
export type Market = {
  id: string;
  url?: string;
  question: string;
  description: string;
  slug: string;
  category: string;
  liquidity: string;
  volume: string;
  end_at: string;
  active: boolean;
  resolved: boolean;
  books: Record<string, Book>;
  version: string;
  resolution_source: string;
};
export type Activity = {
  id: string;
  at: string;
  kind: string;
  message: string;
  agent_id: string | null;
  details?: Record<string, unknown> | null;
};
export type State = {
  id: string;
  mode: "live" | "demo";
  status: "RUNNING" | "FINISHED";
  started_at: string;
  end_at: string;
  updated_at: string;
  last_market_sync?: string;
  health?: {cycle_count: number; completed_at: string; duration_seconds: number; market_count: number; market_provider_ok: boolean; policy_version: string; trigger?: string; logs_url?: string; last_scheduled_cycle?: string};
  agents: Agent[];
  markets: Record<string, Market>;
  events: Activity[];
  history: ({ at: string } & Record<string, Snapshot | string>)[];
  fx: {
    usd_per_eur: string;
    reference_date: string;
    source: string;
    method: string;
  };
  report: null | {
    roi_winner: string;
    absolute_winner: string;
    incomplete_valuation: boolean;
    close_delay_seconds: number;
    limitation: string;
    strategies: Record<string, unknown>;
    ranking: {
      agent_id: string;
      roi: string;
      profit_eur: string;
      survives: boolean;
      return_over_max_drawdown: string | null;
    }[];
  };
};
