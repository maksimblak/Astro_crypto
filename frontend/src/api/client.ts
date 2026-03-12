import type { TodayData, CalendarDay, DailyPrice, PivotPoint, StatsData, RegimeData, UpdateStatus } from '../types/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

export const api = {
  today: () => fetchJson<TodayData>('/api/today'),
  calendar: () => fetchJson<CalendarDay[]>('/api/calendar'),
  daily: () => fetchJson<DailyPrice[]>('/api/daily'),
  pivots: () => fetchJson<PivotPoint[]>('/api/pivots'),
  stats: () => fetchJson<StatsData>('/api/stats'),
  regime: () => fetchJson<RegimeData>('/api/regime'),
  updateStatus: () => fetchJson<UpdateStatus>('/api/update-status'),
};
