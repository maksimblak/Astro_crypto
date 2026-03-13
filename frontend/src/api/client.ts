import type {
  TodayData,
  CalendarDay,
  DailyPrice,
  PivotPoint,
  StatsData,
  RegimeData,
  CycleData,
  UpdateStatus,
  BacktestData,
} from '../types/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

export interface BacktestParams {
  buyThreshold?: number;
  sellThreshold?: number;
  holdDays?: number;
  positionSize?: number;
  useDirection?: boolean;
  sampleSplit?: string;
}

function buildBacktestUrl(params: BacktestParams = {}): string {
  const qs = new URLSearchParams();
  if (params.buyThreshold !== undefined) qs.set('buy_threshold', String(params.buyThreshold));
  if (params.sellThreshold !== undefined) qs.set('sell_threshold', String(params.sellThreshold));
  if (params.holdDays !== undefined) qs.set('hold_days', String(params.holdDays));
  if (params.positionSize !== undefined) qs.set('position_size', String(params.positionSize));
  if (params.useDirection !== undefined) qs.set('use_direction', String(params.useDirection));
  if (params.sampleSplit !== undefined) qs.set('sample_split', params.sampleSplit);
  const query = qs.toString();
  return query ? `/api/backtest?${query}` : '/api/backtest';
}

export const api = {
  today: () => fetchJson<TodayData>('/api/today'),
  calendar: () => fetchJson<CalendarDay[]>('/api/calendar'),
  daily: () => fetchJson<DailyPrice[]>('/api/daily'),
  pivots: () => fetchJson<PivotPoint[]>('/api/pivots'),
  stats: () => fetchJson<StatsData>('/api/stats'),
  regime: () => fetchJson<RegimeData>('/api/regime'),
  cycle: () => fetchJson<CycleData>('/api/cycle'),
  updateStatus: () => fetchJson<UpdateStatus>('/api/update-status'),
  backtest: (params?: BacktestParams) => fetchJson<BacktestData>(buildBacktestUrl(params)),
};
