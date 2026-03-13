export interface TodayData {
  date: string;
  score: number;
  direction: number;
  moon_sign: string;
  moon_element: string;
  quarter: string;
  eclipse_days: number;
  moon_ingress: number;
  tension: number;
  harmony: number;
  retro_planets: string;
  station_planets: string;
  sun_sign: string;
  sun_element: string;
  details: string;
}

export interface CalendarDay {
  date: string;
  score: number;
  direction: number;
  moon_sign: string;
  moon_element: string;
  quarter: string;
  eclipse_days: number;
  moon_ingress: number;
  tension: number;
  harmony: number;
  retro_planets: string;
  station_planets: string;
  sun_sign: string;
  sun_element: string;
  details: string;
}

export interface DailyPrice {
  date: string;
  close: number;
}

export interface PivotPoint {
  date: string;
  price: number;
  is_high: number;
  tension_count?: number;
  near_eclipse?: number;
}

export interface ThresholdRow {
  threshold: number;
  days_count: number;
  days_pct: number;
  pivots_in_zone: number;
  lift: number;
}

export interface ScoreScale {
  cool: number;
  warm: number;
  hot: number;
  extreme: number;
}

export interface StatsData {
  baseline_avg_score: number;
  pivot_avg_score: number;
  pivot_matched: number;
  total_calendar_days: number;
  total_pivots: number;
  thresholds: ThresholdRow[];
  score_scale: ScoreScale;
  direction_accuracy: number;
  direction_total: number;
  direction_correct: number;
  period_start: string;
  period_end: string;
  period_label: string;
}

export interface Signal {
  label: string;
  value: string;
  tone: 'bull' | 'bear' | 'neutral';
  note: string;
}

export interface RegimeMetrics {
  momentum_90?: number;
  close_vs_200?: number;
  amihud_z_90d?: number;
  range_compression_20d?: number;
  drawdown_ath?: number;
  wiki_views_z_30d?: number;
  fear_greed_value?: number;
  funding_rate_z_30d?: number;
  funding_price_divergence_3d?: number;
  funding_contrarian_bias_3d?: number;
  perp_premium_daily?: number;
  open_interest_delta_1d?: number;
  open_interest_delta_z_30d?: number;
  oi_price_state_1d?: string;
  open_interest_z_30d?: number;
  dxy_close?: number;
  dxy_return_20d?: number;
  dxy_return_z_90d?: number;
  us10y_yield?: number;
  us10y_change_20d_bps?: number;
  us10y_change_z_90d?: number;
  spx_close?: number;
  btc_spx_corr_30d?: number;
  unique_addresses_z_30d?: number;
}

export interface RegimeHistory {
  date: string;
  close: number;
  direction_score: number;
  regime_score?: number;
  stress_score: number;
  context_score: number;
  regime_label: string;
  confidence: number;
  stress_label: string;
  context_label: string;
  funding_price_divergence_3d?: number;
  open_interest_delta_1d?: number;
  btc_spx_corr_30d?: number;
}

export interface RegimeData {
  regime_code: string;
  regime_label: string;
  summary: string;
  bias: string;
  confidence: number;
  direction_score: number;
  stress_score: number;
  stress_label: string;
  stress_tone: string;
  context_score: number;
  context_label: string;
  context_tone: string;
  setup_score: number;
  setup_label: string;
  setup_summary: string;
  setup_tone: string;
  price: number;
  as_of: string;
  metrics: RegimeMetrics;
  direction_signals: Signal[];
  stress_signals: Signal[];
  context_signals: Signal[];
  history: RegimeHistory[];
  error?: string;
}

export interface CycleMetrics {
  mvrv_zscore?: number | null;
  mvrv_top_threshold?: number | null;
  mvrv_bottom_extreme?: number | null;
  nupl?: number | null;
  nupl_top_threshold?: number | null;
  nupl_bottom_extreme?: number | null;
  puell_multiple?: number | null;
  puell_top_threshold?: number | null;
  puell_bottom_extreme?: number | null;
  pi_sma111?: number | null;
  pi_sma350x2?: number | null;
  pi_cycle_signal?: number | null;
  hashrate_sma_30?: number | null;
  hashrate_sma_60?: number | null;
  hashribbon_trend?: string | null;
  hashribbon_buy_signal?: number | null;
}

export interface CycleHistory {
  date: string;
  price?: number | null;
  top_score: number;
  bottom_score: number;
  cycle_bias: number;
  cycle_zone: string;
  mvrv_zscore?: number | null;
  nupl?: number | null;
  puell_multiple?: number | null;
  pi_cycle_signal?: number | null;
  hashribbon_buy_signal?: number | null;
}

export interface CycleProjections {
  reference_date: string;
  current_price: number;
  power_law: {
    fair_value: number;
    band_1sigma: [number, number];
    band_2sigma: [number, number];
    position: number;
    r_squared: number;
    slope: number;
    intercept: number;
    fair_at_projected_peak: number;
    band_at_projected_peak: [number, number];
  };
  golden_ratio: {
    sma350: number;
    levels: { fib: number; price: number }[];
    current_ceiling: {
      fib_level: number;
      projected_ceiling: number;
      next_cycle_fib: number;
      next_cycle_ceiling: number;
    };
  };
  halving_timing: {
    last_halving: string;
    projected_peak: string;
    peak_window_early: string;
    peak_window_late: string;
    days_to_projected_peak: number;
    halving_model: {
      history: { halving: string; peak: string; days: number; confirmed: boolean }[];
      avg_days: number;
      std_days: number;
      recent_cycles_used: number;
    };
    top_to_top_avg_days: number;
    top_to_top_projection: string;
    next_halving_est: string;
  };
  diminishing_returns: {
    cycle_rois: { cycle: number; bottom: number; top: number; roi_x: number; confirmed: boolean }[];
    decay_factors: number[];
    avg_decay: number;
    current_cycle_bottom: number;
    current_cycle_top: number;
    current_cycle_roi_x: number;
    current_cycle_projected_roi_x: number;
    current_cycle_projected_peak: number;
    current_outperformance: number;
    projected_next_roi_x: number;
    projected_next_roi_conservative_x: number;
    projected_peak_from_bottom: number;
    projected_peak_conservative: number;
    bear_drawdowns: number[];
    projected_next_drawdown_pct: number;
    projected_next_bottom: number;
  };
  mayer_multiple: number | null;
  pi_cycle_distance: number | null;
  sma200: number;
  sma111: number;
  sma350x2: number;
  composite: {
    projected_peak_date: string;
    days_to_peak: number;
    peak_window: [string, string];
    peak_passed: boolean;
    top_to_top_check: string;
    current_cycle_targets: number[];
    current_cycle_median: number | null;
    next_cycle_targets: number[];
    next_cycle_median: number | null;
    next_cycle_peak_est: string;
  };
}

export interface CycleData {
  as_of: string;
  price?: number | null;
  cycle_zone: string;
  cycle_label: string;
  cycle_tone: 'bull' | 'bear' | 'neutral';
  summary: string;
  top_score: number;
  bottom_score: number;
  cycle_bias: number;
  metrics: CycleMetrics;
  signals: Signal[];
  history: CycleHistory[];
  projections?: CycleProjections | null;
  error?: string;
}

export interface UpdateStatus {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  startup_delay_seconds: number;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  last_stage?: string | null;
  log_path: string;
  status_path: string;
}

export interface BacktestTrade {
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  pnl_pct: number;
  pnl_usd: number;
  hold_days: number;
  entry_score: number;
  exit_score: number;
}

export interface BacktestEquityPoint {
  date: string;
  equity: number;
  close: number;
  score: number;
  in_position: boolean;
}

export interface BacktestMonthly {
  month: string;
  return_pct: number;
}

export interface BacktestConfig {
  buy_score_threshold: number;
  sell_score_threshold: number;
  hold_days: number;
  initial_capital: number;
  position_size: number;
  use_direction: boolean;
  sample_split: string;
}

export interface BacktestData {
  config: BacktestConfig;
  total_return_pct: number;
  buy_hold_return_pct: number;
  sharpe_ratio: number | null;
  max_drawdown_pct: number;
  win_rate: number;
  total_trades: number;
  avg_trade_pnl_pct: number;
  avg_hold_days: number;
  exposure_pct: number;
  trades: BacktestTrade[];
  equity_curve: BacktestEquityPoint[];
  monthly_returns: BacktestMonthly[];
  period_start: string;
  period_end: string;
  total_days: number;
}
