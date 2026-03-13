import type { RegimeData, RegimeMetrics } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { fmtUsd, regimeTone, stressTone } from '../../utils/format';
import SignalCard from './SignalCard';
import RegimeChart from './RegimeChart';

interface Props {
  data: RegimeData;
}

/* ═══ Helpers ═══ */

const DASH = '\u2014';

function fmt(v: number | null | undefined, suffix = ''): string {
  if (v == null) return DASH;
  return `${v}${suffix}`;
}

/** Color class for z-score type values: extreme → colored, mild → neutral */
function zTone(v: number | null | undefined, invert = false): string {
  if (v == null) return '';
  const abs = Math.abs(v);
  if (abs < 1.5) return '';
  const positive = invert ? v < 0 : v > 0;
  return positive ? 'val-bull' : 'val-bear';
}

/** Color class for percentage change values */
function pctTone(v: number | null | undefined, invert = false): string {
  if (v == null) return '';
  const abs = Math.abs(v);
  if (abs < 5) return '';
  const positive = invert ? v < 0 : v > 0;
  return positive ? 'val-bull' : 'val-bear';
}

const OI_STATE_LABELS: Record<string, string> = {
  long_build: 'Long build',
  short_build: 'Short build',
  short_cover: 'Short cover',
  long_unwind: 'Long unwind',
  unchanged: 'Unchanged',
};

const OI_STATE_TONES: Record<string, string> = {
  long_build: 'val-bull',
  short_cover: 'val-bull',
  short_build: 'val-bear',
  long_unwind: 'val-bear',
};

/* ═══ SVG Score Arc (semicircle gauge) ═══ */

const ARC_COLORS = { bull: 'var(--bull)', bear: 'var(--bear)', neutral: 'var(--neon-cyan)' } as const;
const ARC_GLOWS = { bull: 'var(--glow-green)', bear: 'var(--glow-red)', neutral: 'var(--glow-cyan)' } as const;

function ScoreArc({ value, min, max, label, tone }: {
  value: number; min: number; max: number; label: string; tone: 'bull' | 'bear' | 'neutral';
}) {
  const R = 54, CX = 60, CY = 60;
  const half = Math.PI * R;
  const raw = (value - min) / (max - min);
  const ratio = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0;
  const filled = half * ratio;

  return (
    <div className="rg-arc-card">
      <svg viewBox="0 0 120 68" className="rg-arc-svg" role="img" aria-label={`${label}: ${value}`}>
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="7" strokeLinecap="round"
        />
        <path
          d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
          fill="none" stroke={ARC_COLORS[tone]} strokeWidth="7" strokeLinecap="round"
          strokeDasharray={`${filled} ${half}`}
          style={{ filter: `drop-shadow(${ARC_GLOWS[tone]})`, transition: 'stroke-dasharray 0.8s ease' }}
        />
      </svg>
      <div className="rg-arc-value" style={{ color: ARC_COLORS[tone] }}>
        {value > 0 ? '+' : ''}{value}
      </div>
      <div className="rg-arc-label">{label}</div>
    </div>
  );
}

/* ═══ Z-score bar — shows position from -3σ to +3σ ═══ */

function ZBar({ value, label, invert = false }: {
  value: number | null | undefined; label?: string; invert?: boolean;
}) {
  if (value == null) return null;
  const clamped = Math.max(-3, Math.min(3, value));
  const pct = ((clamped + 3) / 6) * 100;
  const abs = Math.abs(value);
  let color = 'var(--text3)';
  if (abs >= 2) color = (invert ? value < 0 : value > 0) ? 'var(--bull)' : 'var(--bear)';
  else if (abs >= 1.5) color = (invert ? value < 0 : value > 0) ? 'rgba(0,255,136,0.5)' : 'rgba(255,59,92,0.5)';

  return (
    <div className="rg-zbar">
      {label && <span className="rg-zbar-label">{label}</span>}
      <div className="rg-zbar-track">
        <div className="rg-zbar-center" />
        <div className="rg-zbar-dot" style={{ left: `${pct}%`, background: color, boxShadow: abs >= 2 ? `0 0 8px ${color}` : 'none' }} />
      </div>
    </div>
  );
}

/* ═══ Metric card with optional z-bar ═══ */

function MetricCard({ label, value, sub, tone, zValue, zInvert }: {
  label: string; value: string; sub: string; tone?: string;
  zValue?: number | null; zInvert?: boolean;
}) {
  return (
    <div className="rg-metric">
      <div className="rg-metric-label">{label}</div>
      <div className={`rg-metric-value ${tone || ''}`}>{value}</div>
      {zValue != null && <ZBar value={zValue} invert={zInvert} />}
      <div className="rg-metric-sub">{sub}</div>
    </div>
  );
}

/* ═══ Main Component ═══ */

export default function RegimeSection({ data }: Props) {
  if (data.error) {
    return (
      <div className="section" id="sectionRegime">
        <div className="section-head">
          <div className="section-title">
            <span className="dot" style={{ background: 'var(--bull)', boxShadow: 'var(--glow-green)' }} />
            Рыночный режим
          </div>
        </div>
        <div className="card">
          <div className="loading" style={{ animation: 'none' }}>{data.error}</div>
        </div>
      </div>
    );
  }

  const tone = regimeTone(data.regime_code);
  const stressChipTone = stressTone(data.stress_tone);
  const contextChipTone = stressTone(data.context_tone);
  const setupTone_ = stressTone(data.setup_tone);
  const m = data.metrics ?? ({} as RegimeMetrics);

  const biasLabel = data.bias === 'risk-on' ? 'Risk-on'
    : data.bias === 'risk-off' ? 'Risk-off' : 'Нейтрально';

  const oiState = m.oi_price_state_1d;
  const oiLabel = oiState ? (OI_STATE_LABELS[oiState] ?? DASH) : DASH;
  const oiTone = oiState ? (OI_STATE_TONES[oiState] ?? '') : '';

  return (
    <div className="section" id="sectionRegime">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--bull)', boxShadow: 'var(--glow-green)' }} />
          Рыночный режим
        </div>
      </div>
      <div className="card">

        {/* ── Hero: Setup + Regime + Arcs ── */}
        <div className="rg-hero">
          {/* Setup banner */}
          <div className={`rg-setup ${setupTone_}`}>
            <div className="rg-setup-score-wrap">
              <div className={`rg-setup-score ${setupTone_}`}>
                {data.setup_score > 0 ? '+' : ''}{data.setup_score}
              </div>
              <div className="rg-setup-kicker">Daily setup</div>
            </div>
            <div className="rg-setup-info">
              <div className="rg-setup-label">{data.setup_label}</div>
              <div className="rg-setup-text">{data.setup_summary}</div>
            </div>
          </div>

          {/* Regime card + Score arcs */}
          <div className="rg-hero-bottom">
            <div className={`rg-regime-card ${tone}`}>
              <div className="rg-regime-kicker">Режим на {fmtDate(data.as_of)}</div>
              <div className="rg-regime-title">{data.regime_label}</div>
              <div className="rg-regime-summary">{data.summary}</div>
              <div className="rg-chips">
                <span className={`rg-chip ${tone}`}>{biasLabel}</span>
                <span className={`rg-chip ${stressChipTone}`}>{data.stress_label}</span>
                <span className={`rg-chip ${contextChipTone}`}>{data.context_label}</span>
                <span className={`rg-chip ${tone}`}>{data.confidence}% confidence</span>
              </div>
            </div>

            <div className="rg-arcs">
              <ScoreArc value={data.direction_score} min={-18} max={18} label="Direction" tone={data.direction_score >= 0 ? 'bull' : 'bear'} />
              <ScoreArc value={data.stress_score} min={0} max={12} label="Stress" tone={data.stress_score >= 6 ? 'bear' : data.stress_score >= 3 ? 'neutral' : 'bull'} />
              <ScoreArc value={data.context_score} min={-8} max={8} label="Context" tone={data.context_score >= 2 ? 'bull' : data.context_score <= -2 ? 'bear' : 'neutral'} />
            </div>

            {/* BTC price card */}
            <div className="rg-price-card">
              <div className="rg-price-kicker">BTC</div>
              <div className="rg-price-value">{fmtUsd(data.price)}</div>
              <div className="rg-price-date">на {fmtDate(data.as_of)}</div>
              <div className="rg-price-stats">
                <div className="rg-price-stat">
                  <span className="rg-price-stat-label">Momentum 90д</span>
                  <span className={`rg-price-stat-value ${pctTone(m.momentum_90)}`}>{fmt(m.momentum_90, '%')}</span>
                </div>
                <div className="rg-price-stat">
                  <span className="rg-price-stat-label">vs 200DMA</span>
                  <span className={`rg-price-stat-value ${pctTone(m.close_vs_200)}`}>{fmt(m.close_vs_200, '%')}</span>
                </div>
                <div className="rg-price-stat">
                  <span className="rg-price-stat-label">От ATH</span>
                  <span className={`rg-price-stat-value ${pctTone(m.drawdown_ath)}`}>{fmt(m.drawdown_ath, '%')}</span>
                </div>
                <div className="rg-price-stat">
                  <span className="rg-price-stat-label">Confidence</span>
                  <span className="rg-price-stat-value">{data.confidence}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Metric Groups ── */}
        <div className="rg-groups">

          {/* Volatility & Liquidity */}
          <div className="rg-group">
            <div className="rg-group-title">Volatility & Liquidity</div>
            <div className="rg-group-grid rg-group-grid-3">
              <MetricCard label="Amihud Z" value={fmt(m.amihud_z_90d)} sub="Liquidity stress vs 90д baseline" tone={zTone(m.amihud_z_90d, true)} zValue={m.amihud_z_90d} zInvert />
              <MetricCard label="Range State" value={fmt(m.range_compression_20d, 'x')} sub="Текущий диапазон vs median 20д" />
              <MetricCard label="Fear & Greed" value={fmt(m.fear_greed_value)} sub="Сантимент толпы 0-100" tone={m.fear_greed_value != null ? (m.fear_greed_value <= 25 ? 'val-bear' : m.fear_greed_value >= 75 ? 'val-bull' : '') : ''} />
            </div>
          </div>

          {/* Sentiment & Attention */}
          <div className="rg-group">
            <div className="rg-group-title">Sentiment & Attention</div>
            <div className="rg-group-grid rg-group-grid-2">
              <MetricCard label="Wikipedia Z" value={fmt(m.wiki_views_z_30d)} sub="Внешнее внимание к BTC vs 30д" tone={zTone(m.wiki_views_z_30d, true)} zValue={m.wiki_views_z_30d} zInvert />
              <MetricCard label="Active Addr Z" value={fmt(m.unique_addresses_z_30d)} sub="Сильнейший on-chain сигнал" tone={zTone(m.unique_addresses_z_30d)} zValue={m.unique_addresses_z_30d} />
            </div>
          </div>

          {/* Derivatives */}
          <div className="rg-group">
            <div className="rg-group-title">Derivatives</div>
            <div className="rg-group-grid rg-group-grid-4">
              <MetricCard label="Funding Z" value={fmt(m.funding_rate_z_30d)} sub="Watchlist: не в context score" tone={zTone(m.funding_rate_z_30d)} zValue={m.funding_rate_z_30d} />
              <MetricCard label="Funding Divergence" value={fmt(m.funding_price_divergence_3d)} sub="+ = price и funding расходятся" tone={zTone(m.funding_price_divergence_3d, true)} />
              <MetricCard label="Perp Premium" value={fmt(m.perp_premium_daily, '%')} sub="Премия perpetual к spot" tone={pctTone(m.perp_premium_daily)} />
              <MetricCard label="OI State" value={oiLabel} sub="Build / unwind / cover" tone={oiTone} />
              <MetricCard label="OI Delta 1д" value={fmt(m.open_interest_delta_1d, '%')} sub="Дневное изменение OI" />
              <MetricCard label="OI Delta Z" value={fmt(m.open_interest_delta_z_30d)} sub="Необычность изменения" tone={zTone(m.open_interest_delta_z_30d)} zValue={m.open_interest_delta_z_30d} />
              <MetricCard label="OI Z" value={fmt(m.open_interest_z_30d)} sub="Насколько раздут OI" tone={zTone(m.open_interest_z_30d)} zValue={m.open_interest_z_30d} />
            </div>
          </div>

          {/* Macro */}
          <div className="rg-group">
            <div className="rg-group-title">Macro</div>
            <div className="rg-group-grid rg-group-grid-3">
              <div className="rg-metric rg-metric-wide">
                <div className="rg-metric-label">DXY</div>
                <div className="rg-metric-row">
                  <div>
                    <div className={`rg-metric-value ${pctTone(m.dxy_return_20d, true)}`}>{fmt(m.dxy_return_20d, '%')}</div>
                    <div className="rg-metric-sub">20д change</div>
                  </div>
                  <div>
                    <div className={`rg-metric-value ${zTone(m.dxy_return_z_90d, true)}`}>{fmt(m.dxy_return_z_90d)}</div>
                    <div className="rg-metric-sub">Z-score</div>
                  </div>
                </div>
                <ZBar value={m.dxy_return_z_90d} invert />
              </div>
              <div className="rg-metric rg-metric-wide">
                <div className="rg-metric-label">US10Y</div>
                <div className="rg-metric-row">
                  <div>
                    <div className={`rg-metric-value ${(m.us10y_change_20d_bps ?? 0) > 20 ? 'val-bear' : ''}`}>{fmt(m.us10y_change_20d_bps)} <small>bps</small></div>
                    <div className="rg-metric-sub">20д change</div>
                  </div>
                  <div>
                    <div className={`rg-metric-value ${zTone(m.us10y_change_z_90d, true)}`}>{fmt(m.us10y_change_z_90d)}</div>
                    <div className="rg-metric-sub">Z-score</div>
                  </div>
                </div>
                <ZBar value={m.us10y_change_z_90d} invert />
              </div>
              <MetricCard label="BTC/SPX Corr" value={fmt(m.btc_spx_corr_30d)} sub="Высокая = macro доминирует" tone={(m.btc_spx_corr_30d ?? 0) > 0.6 ? 'val-bear' : ''} />
            </div>
          </div>
        </div>

        {/* ── Signals ── */}
        <div className="rg-signals">
          <div className="rg-signal-section">
            <div className="rg-signal-title">Direction signals</div>
            <div className="signal-grid">
              {data.direction_signals.map(s => <SignalCard key={s.label} signal={s} />)}
            </div>
          </div>
          <div className="rg-signal-section">
            <div className="rg-signal-title">Stress signals</div>
            <div className="signal-grid">
              {data.stress_signals.map(s => <SignalCard key={s.label} signal={s} />)}
            </div>
          </div>
          <div className="rg-signal-section">
            <div className="rg-signal-title">External context</div>
            <div className="signal-grid">
              {data.context_signals.map(s => <SignalCard key={s.label} signal={s} />)}
            </div>
          </div>
        </div>

        {/* ── Chart ── */}
        {data.history?.length > 0 && <RegimeChart history={data.history} />}
      </div>
    </div>
  );
}
