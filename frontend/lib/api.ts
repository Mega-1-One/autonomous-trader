// Shared API client (C-05): config-driven base URL, optional bearer token.
//
// - NEXT_PUBLIC_API_URL (default http://localhost:8000)
// - NEXT_PUBLIC_API_TOKEN: when set, every request carries
//   `Authorization: Bearer <token>` so the dashboard keeps working when the
//   backend enforces the D-01 production token gate.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_TOKEN: string | undefined = process.env.NEXT_PUBLIC_API_TOKEN;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const headers: Record<string, string> = {};
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
  return { ...headers, ...((init?.headers as Record<string, string> | undefined) ?? {}) };
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: buildHeaders(init) });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      const candidate = (body as { detail?: unknown; message?: unknown }).detail
        ?? (body as { message?: unknown }).message;
      if (typeof candidate === "string" && candidate.length > 0) detail = candidate;
    } catch {
      // keep the status text
    }
    throw new ApiError(detail, res.status);
  }
  return res;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return (await res.json()) as T;
}

// --- Minimal response types (mirrors backend shapes) ---

export interface HealthResponse {
  status: string;
  app_name: string;
  execution_mode: string;
  enable_live_trading: boolean;
  live_trading_confirmation: boolean;
  database_connected: boolean;
  mt5_connected: boolean;
  mt5_adapter?: string;
  simulated_execution?: boolean;
  timestamp: string;
}

export interface RiskParameters {
  risk_per_trade_percent: number;
  maximum_daily_loss_percent: number;
  maximum_trades_per_day: number;
  maximum_open_positions: number;
  maximum_spread_pips: number;
  minimum_rr: number;
}

export interface RiskStatusResponse {
  emergency_stop_active: boolean;
  daily_lock_active: boolean;
  daily_lock_reason: string | null;
  today_trade_count: number;
  today_realized_pnl: number;
  risk_parameters: RiskParameters;
}

export interface PositionRecord {
  position_id: string;
  symbol: string;
  direction: string;
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  floating_pnl: number;
  r_multiple: number;
  status: string;
}

export interface PositionsResponse {
  total_positions: number;
  open_positions: PositionRecord[];
  closed_positions: PositionRecord[];
}

export interface StrategySignal {
  client_signal_id: string;
  symbol: string;
  direction: string;
  setup_type: string;
  status: string;
  risk_reward: number;
  reasons: Record<string, unknown>;
}

export interface SignalResponse {
  symbol: string;
  signal: StrategySignal;
}

export interface FvgItem {
  fvg_type: string;
  lower_boundary: number;
  upper_boundary: number;
  mitigation_status: string;
  fill_percentage: number;
}

export interface PatternResponse {
  symbol: string;
  timeframe: string;
  trend: string;
  displacements: unknown[];
  fair_value_gaps: FvgItem[];
  liquidity_sweeps: unknown[];
  order_blocks: unknown[];
}

export interface BacktestReport {
  total_trades: number;
  net_profit: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_percent: number;
  expectancy: number;
  sharpe_ratio: number;
  sortino_ratio: number;
}

export interface MonteCarloSimulation {
  probability_of_ruin_percent: number;
  median_net_profit: number;
  median_max_drawdown_percent: number;
  expected_losing_streak: number;
}
