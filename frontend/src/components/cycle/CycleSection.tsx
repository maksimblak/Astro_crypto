import type { CycleData, CycleHistory, CycleProjections } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { fmtUsd } from '../../utils/format';
import SignalCard from '../regime/SignalCard';
import CycleChart from './CycleChart';

interface Props {
  data?: CycleData;
  error?: string;
}

/* ═══ Helpers ═══ */

function zoneLabel(zone: string): string {
  const map: Record<string, string> = {
    top_zone: 'Top zone',
    top_watch: 'Top watch',
    bottom_zone: 'Bottom zone',
    bottom_watch: 'Bottom watch',
    mixed: 'Mixed',
  };
  return map[zone] || 'Neutral';
}

function zoneTone(zone: string): 'bull' | 'bear' | 'neutral' {
  if (zone === 'top_zone' || zone === 'top_watch') return 'bear';
  if (zone === 'bottom_zone' || zone === 'bottom_watch') return 'bull';
  return 'neutral';
}

function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value == null) return '\u2014';
  return value.toFixed(digits);
}

function fmtCompact(v: number): string {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return v.toFixed(0);
}

function flaggedRows(history: CycleHistory[]): CycleHistory[] {
  return history
    .filter(
      p =>
        p.top_score >= 0.45 ||
        p.bottom_score >= 0.45 ||
        p.pi_cycle_signal === 1 ||
        p.hashribbon_buy_signal === 1,
    )
    .slice(-12)
    .reverse();
}

function plPositionLabel(pos: number): string {
  if (pos >= 0.85) return 'Сильно выше тренда';
  if (pos >= 0.65) return 'Выше тренда';
  if (pos >= 0.45) return 'На тренде';
  if (pos >= 0.25) return 'Ниже тренда';
  return 'Сильно ниже тренда';
}

function plPositionTone(pos: number): string {
  if (pos >= 0.80) return 'bear';
  if (pos >= 0.60) return 'neutral';
  return 'bull';
}

/* ═══ Visual Sub-components ═══ */

function ScoreArc({ value, label, color }: { value: number; label: string; color: string }) {
  const pct = Math.max(0, Math.min(1, value));
  const r = 36;
  const arcLen = Math.PI * r;

  return (
    <div className="score-arc-card">
      <svg width="100" height="56" viewBox="0 0 100 56" className="score-arc-svg">
        <path
          d="M 14 50 A 36 36 0 0 1 86 50"
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        {pct > 0.005 && (
          <path
            d="M 14 50 A 36 36 0 0 1 86 50"
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={`${arcLen * pct} ${arcLen}`}
            className="score-arc-fill"
            style={{ filter: `drop-shadow(0 0 8px ${color}60)` }}
          />
        )}
      </svg>
      <div className="score-arc-pct" style={{ color }}>
        {(pct * 100).toFixed(0)}%
      </div>
      <div className="score-arc-label">{label}</div>
    </div>
  );
}

function BiasBar({ bias }: { bias: number }) {
  const pos = Math.max(2, Math.min(98, (bias + 1) / 2 * 100));
  return (
    <div className="bias-bar">
      <div className="bias-bar-track">
        <div className="bias-bar-marker" style={{ left: `${pos}%` }} />
      </div>
      <div className="bias-bar-labels">
        <span>Bottom</span>
        <span>Top</span>
      </div>
    </div>
  );
}

function ThresholdBar({
  value,
  bottom,
  top,
}: {
  value: number | null | undefined;
  bottom: number | null | undefined;
  top: number | null | undefined;
}) {
  if (value == null || bottom == null || top == null) return null;
  const range = top - bottom;
  if (range <= 0) return null;
  const pos = Math.max(2, Math.min(98, ((value - bottom) / range) * 100));
  let color = 'var(--neon-cyan)';
  if (pos >= 85) color = 'var(--bear)';
  else if (pos >= 65) color = 'var(--warn)';
  else if (pos <= 15) color = 'var(--bull)';

  return (
    <div className="threshold-bar">
      <div className="threshold-track">
        <div
          className="threshold-marker"
          style={{
            left: `${pos}%`,
            background: color,
            boxShadow: `0 0 8px ${color}`,
          }}
        />
      </div>
      <div className="threshold-labels">
        <span>{bottom.toFixed(2)}</span>
        <span>{top.toFixed(2)}</span>
      </div>
    </div>
  );
}

/* ═══ ProjectionBlock ═══ */

function ProjectionBlock({ proj }: { proj: CycleProjections }) {
  const pl = proj.power_law;
  const gr = proj.golden_ratio;
  const ht = proj.halving_timing;
  const dr = proj.diminishing_returns;
  const comp = proj.composite;
  const peakPassed = comp.peak_passed;

  return (
    <>
      <div className="metric-group">
        <div className="metric-group-title">Текущий цикл (халвинг 2024)</div>

        <div className="projection-summary">
          <div className={`projection-card highlight ${peakPassed ? 'warn' : ''}`}>
            <div className="label">Прогноз пика</div>
            <div className="value">{fmtDate(comp.projected_peak_date)}</div>
            <div className="sub">
              {peakPassed
                ? `Окно пика закрылось ${Math.abs(comp.days_to_peak)}д назад`
                : comp.days_to_peak > 0
                  ? `Через ${comp.days_to_peak} дней`
                  : `${Math.abs(comp.days_to_peak)}д назад, но окно до ${fmtDate(comp.peak_window[1])}`}
            </div>
          </div>
          <div className="projection-card highlight">
            <div className="label">Median target</div>
            <div className="value">
              {comp.current_cycle_median ? fmtUsd(comp.current_cycle_median) : '\u2014'}
            </div>
            <div className="sub">
              {comp.current_cycle_targets.length > 0 &&
                `${fmtUsd(comp.current_cycle_targets[0])} \u2013 ${fmtUsd(comp.current_cycle_targets[comp.current_cycle_targets.length - 1])}`}
            </div>
          </div>
          <div className="projection-card highlight">
            <div className="label">Окно пика</div>
            <div className="value">{fmtDate(comp.peak_window[0])}</div>
            <div className="sub">до {fmtDate(comp.peak_window[1])}</div>
          </div>
          <div className="projection-card highlight">
            <div className="label">Top-to-top check</div>
            <div className="value">{fmtDate(comp.top_to_top_check)}</div>
            <div className="sub">Avg {ht.top_to_top_avg_days}д между топами</div>
          </div>
        </div>

        {peakPassed && (
          <div
            className="projection-card warn-banner"
            style={{ marginTop: '0.5rem', padding: '10px 14px', opacity: 0.85 }}
          >
            Модель считает что пик текущего цикла вероятно уже произошёл (ATH{' '}
            {fmtUsd(dr.current_cycle_top)}). Цена ниже ATH на{' '}
            {((1 - proj.current_price / dr.current_cycle_top) * 100).toFixed(0)}%.
          </div>
        )}
      </div>

      <div className="metric-group">
        <div className="metric-group-title">Модели текущего цикла</div>
        <div className="signal-grid">
          <div className={`signal-card ${plPositionTone(pl.position)}`}>
            <div className="signal-label">POWER LAW</div>
            <div className="signal-value">{fmtUsd(pl.fair_value)}</div>
            <div className="signal-note">
              Fair value (R²={pl.r_squared.toFixed(2)}). Позиция: {(pl.position * 100).toFixed(0)}%
              — {plPositionLabel(pl.position)}. Коридор ±1σ: {fmtUsd(pl.band_1sigma[0])} –{' '}
              {fmtUsd(pl.band_1sigma[1])}.
            </div>
          </div>

          <div className="signal-card neutral">
            <div className="signal-label">GOLDEN RATIO ×{gr.current_ceiling.fib_level}</div>
            <div className="signal-value">{fmtUsd(gr.current_ceiling.projected_ceiling)}</div>
            <div className="signal-note">
              350DMA = {fmtUsd(gr.sma350)}. Ceiling текущего цикла: ×
              {gr.current_ceiling.fib_level} = {fmtUsd(gr.current_ceiling.projected_ceiling)}.
            </div>
          </div>

          <div className={`signal-card ${peakPassed ? 'bear' : 'neutral'}`}>
            <div className="signal-label">HALVING TIMING</div>
            <div className="signal-value">{fmtDate(ht.projected_peak)}</div>
            <div className="signal-note">
              Халвинг: {fmtDate(ht.last_halving)}. Avg {ht.halving_model?.avg_days ?? '\u2014'}д до
              пика (3 цикла). Окно: {fmtDate(ht.peak_window_early)} –{' '}
              {fmtDate(ht.peak_window_late)}.
            </div>
          </div>

          <div
            className={`signal-card ${
              proj.mayer_multiple != null && proj.mayer_multiple > 2.4
                ? 'bear'
                : proj.mayer_multiple != null && proj.mayer_multiple < 0.8
                  ? 'bull'
                  : 'neutral'
            }`}
          >
            <div className="signal-label">MAYER MULTIPLE</div>
            <div className="signal-value">
              {proj.mayer_multiple != null ? proj.mayer_multiple.toFixed(2) : '\u2014'}
            </div>
            <div className="signal-note">
              Price / 200DMA ({fmtUsd(proj.sma200)}). Top &gt; 2.4, bottom &lt; 0.5.
            </div>
          </div>

          <div
            className={`signal-card ${
              proj.pi_cycle_distance != null && proj.pi_cycle_distance > -0.02 ? 'bear' : 'neutral'
            }`}
          >
            <div className="signal-label">PI CYCLE DISTANCE</div>
            <div className="signal-value">
              {proj.pi_cycle_distance != null
                ? (proj.pi_cycle_distance * 100).toFixed(1) + '%'
                : '\u2014'}
            </div>
            <div className="signal-note">
              111DMA до 2×350DMA. 0% = top crossover. Сейчас{' '}
              {proj.pi_cycle_distance != null && proj.pi_cycle_distance < 0 ? 'ниже' : 'выше'}.
            </div>
          </div>

          <div className={`signal-card ${dr.current_outperformance >= 1 ? 'bull' : 'bear'}`}>
            <div className="signal-label">DIMINISHING RETURNS (тек.)</div>
            <div className="signal-value">{dr.current_cycle_roi_x}×</div>
            <div className="signal-note">
              ATH {fmtUsd(dr.current_cycle_top)} от дна {fmtUsd(dr.current_cycle_bottom)}. Модель
              ожидала {dr.current_cycle_projected_roi_x}× ={' '}
              {fmtUsd(dr.current_cycle_projected_peak)}.
              {dr.current_outperformance >= 1
                ? ` Перевыполнение ${dr.current_outperformance}×.`
                : ` Недобор до модели.`}
            </div>
          </div>
        </div>
      </div>

      <div className="metric-group">
        <div className="metric-group-title">Следующий цикл (халвинг ~2028)</div>

        <div className="projection-summary">
          <div className="projection-card">
            <div className="label">Ожидаемый пик</div>
            <div className="value">{fmtDate(comp.next_cycle_peak_est)}</div>
            <div className="sub">Следующий халвинг ~{fmtDate(ht.next_halving_est)}</div>
          </div>
          <div className="projection-card">
            <div className="label">Median target</div>
            <div className="value">
              {comp.next_cycle_median ? fmtUsd(comp.next_cycle_median) : '\u2014'}
            </div>
            <div className="sub">
              {comp.next_cycle_targets.length > 0 &&
                `${fmtUsd(comp.next_cycle_targets[0])} \u2013 ${fmtUsd(comp.next_cycle_targets[comp.next_cycle_targets.length - 1])}`}
            </div>
          </div>
          <div className="projection-card">
            <div className="label">Прогноз просадки</div>
            <div className="value">~{dr.projected_next_drawdown_pct}%</div>
            <div className="sub">Дно ~{fmtUsd(dr.projected_next_bottom)}</div>
          </div>
          <div className="projection-card">
            <div className="label">Golden Ratio ×{gr.current_ceiling.next_cycle_fib}</div>
            <div className="value">{fmtUsd(gr.current_ceiling.next_cycle_ceiling)}</div>
            <div className="sub">350DMA × {gr.current_ceiling.next_cycle_fib}</div>
          </div>
        </div>
      </div>

      {dr.cycle_rois.length > 0 && (
        <div className="metric-group">
          <div className="metric-group-title">ROI по циклам</div>
          <table>
            <thead>
              <tr>
                <th>Цикл</th>
                <th>Дно</th>
                <th>Пик</th>
                <th>ROI</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {dr.cycle_rois.map(r => (
                <tr
                  key={r.cycle}
                  style={r.confirmed ? undefined : { opacity: 0.7, fontStyle: 'italic' }}
                >
                  <td>{r.cycle}</td>
                  <td>{fmtUsd(r.bottom)}</td>
                  <td>{fmtUsd(r.top)}</td>
                  <td className="lift-good">{r.roi_x}×</td>
                  <td style={{ fontSize: '0.8em', opacity: 0.6 }}>
                    {r.confirmed ? '' : 'ATH (не подтв.)'}
                  </td>
                </tr>
              ))}
              <tr style={{ opacity: 0.55, fontStyle: 'italic' }}>
                <td>~2029</td>
                <td>{fmtUsd(dr.projected_next_bottom)}</td>
                <td>
                  {fmtUsd(dr.projected_peak_conservative)} –{' '}
                  {fmtUsd(dr.projected_peak_from_bottom)}
                </td>
                <td>
                  {dr.projected_next_roi_conservative_x}× – {dr.projected_next_roi_x}×
                </td>
                <td style={{ fontSize: '0.8em' }}>прогноз</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/* ═══ Main Component ═══ */

export default function CycleSection({ data, error }: Props) {
  if (error || !data) {
    return (
      <div className="section" id="sectionCycle">
        <div className="section-head">
          <div className="section-title">
            <span
              className="dot"
              style={{ background: 'var(--bear)', boxShadow: 'var(--glow-red)' }}
            />
            Пики и дно BTC
          </div>
        </div>
        <div className="card">
          <div className="loading" style={{ animation: 'none' }}>
            {error || 'Macro cycle layer недоступен.'}
          </div>
        </div>
      </div>
    );
  }

  const tone = zoneTone(data.cycle_zone);
  const flagged = flaggedRows(data.history || []);
  const m = data.metrics;

  const piDistance =
    m?.pi_sma111 && m?.pi_sma350x2 && m.pi_sma350x2 > 0
      ? (m.pi_sma111 / m.pi_sma350x2 - 1) * 100
      : null;

  const piBarPct =
    piDistance != null ? Math.max(2, Math.min(98, 100 - Math.abs(piDistance))) : 0;

  return (
    <div className="section" id="sectionCycle">
      <div className="section-head">
        <div className="section-title">
          <span
            className="dot"
            style={{ background: 'var(--bear)', boxShadow: 'var(--glow-red)' }}
          />
          Пики и дно BTC
        </div>
      </div>
      <div className="card">
        {/* ═══ Hero Section ═══ */}
        <div className="cycle-hero">
          <div className={`cycle-hero-main ${tone}`}>
            <div className="cycle-kicker">Macro cycle layer на {fmtDate(data.as_of)}</div>
            <div className="cycle-title">{data.cycle_label}</div>
            <div className="cycle-copy">{data.summary}</div>
            <BiasBar bias={data.cycle_bias ?? 0} />
            <div className="regime-chips">
              <span className={`regime-chip ${tone}`}>{zoneLabel(data.cycle_zone)}</span>
              <span className="regime-chip neutral">{fmtUsd(data.price)}</span>
              <span
                className={`regime-chip ${(data.cycle_bias ?? 0) >= 0 ? 'bear' : 'bull'}`}
              >
                Bias {(data.cycle_bias ?? 0) > 0 ? '+' : ''}
                {((data.cycle_bias ?? 0) * 100).toFixed(1)}%
              </span>
            </div>
          </div>

          <ScoreArc value={data.top_score ?? 0} label="Top risk" color="#ff3b5c" />
          <ScoreArc value={data.bottom_score ?? 0} label="Bottom signal" color="#00ff88" />

          <div className="cycle-price-card">
            <div className="cpc-label">BTC</div>
            <div className="cpc-price">{fmtUsd(data.price)}</div>
            <div className="cpc-date">{fmtDate(data.as_of)}</div>
            {data.projections?.mayer_multiple != null && (
              <div className="cpc-row">
                <span className="cpc-row-label">Mayer</span>
                <span
                  className="cpc-row-value"
                  style={{
                    color:
                      data.projections.mayer_multiple > 2.4
                        ? 'var(--bear)'
                        : data.projections.mayer_multiple < 0.8
                          ? 'var(--bull)'
                          : 'var(--text)',
                  }}
                >
                  {data.projections.mayer_multiple.toFixed(2)}
                </span>
              </div>
            )}
            {data.projections?.power_law && (
              <div className="cpc-row">
                <span className="cpc-row-label">Power Law</span>
                <span
                  className="cpc-row-value"
                  style={{
                    color:
                      data.projections.power_law.position >= 0.8
                        ? 'var(--bear)'
                        : data.projections.power_law.position <= 0.3
                          ? 'var(--bull)'
                          : 'var(--neon-cyan)',
                  }}
                >
                  {(data.projections.power_law.position * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>
        </div>

        {/* ═══ Valuation Metrics ═══ */}
        <div className="metric-group">
          <div className="metric-group-title">Valuation</div>
          <div className="metric-group-grid">
            <div className="metric-card">
              <div className="m-label">MVRV Z-Score</div>
              <div className="m-value">{fmtNum(m?.mvrv_zscore, 2)}</div>
              <ThresholdBar
                value={m?.mvrv_zscore}
                bottom={m?.mvrv_bottom_extreme}
                top={m?.mvrv_top_threshold}
              />
              <div className="m-sub">
                bottom &lt;{fmtNum(m?.mvrv_bottom_extreme, 2)} &middot; top &gt;
                {fmtNum(m?.mvrv_top_threshold, 2)}
              </div>
            </div>
            <div className="metric-card">
              <div className="m-label">NUPL</div>
              <div className="m-value">{fmtNum(m?.nupl, 3)}</div>
              <ThresholdBar
                value={m?.nupl}
                bottom={m?.nupl_bottom_extreme}
                top={m?.nupl_top_threshold}
              />
              <div className="m-sub">
                bottom &lt;{fmtNum(m?.nupl_bottom_extreme, 3)} &middot; top &gt;
                {fmtNum(m?.nupl_top_threshold, 3)}
              </div>
            </div>
            <div className="metric-card">
              <div className="m-label">Puell Multiple</div>
              <div className="m-value">{fmtNum(m?.puell_multiple, 3)}</div>
              <ThresholdBar
                value={m?.puell_multiple}
                bottom={m?.puell_bottom_extreme}
                top={m?.puell_top_threshold}
              />
              <div className="m-sub">
                bottom &lt;{fmtNum(m?.puell_bottom_extreme, 2)} &middot; top &gt;
                {fmtNum(m?.puell_top_threshold, 2)}
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Timing Indicators ═══ */}
        <div className="metric-group">
          <div className="metric-group-title">Timing</div>
          <div className="metric-group-grid metric-group-wide">
            {/* Pi Cycle */}
            <div className="metric-card">
              <div className="m-label">Pi Cycle Top</div>
              <div
                className="m-value"
                style={{
                  color:
                    piDistance != null && piDistance > -2 ? 'var(--bear)' : 'var(--text)',
                }}
              >
                {piDistance != null ? `${piDistance.toFixed(1)}%` : '\u2014'}
              </div>
              <div className="m-sub-accent">Расстояние 111DMA → 2×350DMA</div>
              {piDistance != null && (
                <div className="pi-distance-bar">
                  <div className="pi-distance-track">
                    <div
                      className="pi-distance-fill"
                      style={{
                        width: `${piBarPct}%`,
                        background:
                          piDistance > -5
                            ? 'var(--bear)'
                            : piDistance > -20
                              ? 'var(--warn)'
                              : 'var(--neon-cyan)',
                      }}
                    />
                    <div className="pi-distance-label-cross">0% = crossover</div>
                  </div>
                </div>
              )}
              <div className="m-row">
                <span className="m-row-label">111DMA</span>
                <span className="m-row-value">
                  {fmtUsd(m?.pi_sma111 ?? undefined)}
                </span>
              </div>
              <div className="m-row">
                <span className="m-row-label">350DMA×2</span>
                <span className="m-row-value">
                  {fmtUsd(m?.pi_sma350x2 ?? undefined)}
                </span>
              </div>
              <div className="m-row">
                <span className="m-row-label">Signal</span>
                <span
                  className="m-row-value"
                  style={{
                    color:
                      m?.pi_cycle_signal === 1
                        ? 'var(--bear)'
                        : m?.pi_cycle_signal === -1
                          ? 'var(--bull)'
                          : 'var(--text2)',
                  }}
                >
                  {m?.pi_cycle_signal === 1
                    ? 'Top cross'
                    : m?.pi_cycle_signal === -1
                      ? 'Down cross'
                      : 'Нет'}
                </span>
              </div>
            </div>

            {/* Hash Ribbons */}
            <div className="metric-card">
              <div className="m-label">Hash Ribbons</div>
              <div
                className="m-value"
                style={{
                  color:
                    m?.hashribbon_trend === 'Up'
                      ? 'var(--bull)'
                      : m?.hashribbon_trend === 'Down'
                        ? 'var(--bear)'
                        : 'var(--text)',
                }}
              >
                {m?.hashribbon_trend || '\u2014'}
              </div>
              <div className="m-sub-accent">
                {m?.hashrate_sma_30 && m?.hashrate_sma_60
                  ? m.hashrate_sma_30 > m.hashrate_sma_60
                    ? '30DMA > 60DMA — майнеры в плюсе'
                    : '30DMA < 60DMA — майнеры под давлением'
                  : 'Hashrate moving averages'}
              </div>
              <div className="m-row">
                <span className="m-row-label">Hashrate 30DMA</span>
                <span className="m-row-value">
                  {m?.hashrate_sma_30 ? fmtCompact(m.hashrate_sma_30) : '\u2014'}
                </span>
              </div>
              <div className="m-row">
                <span className="m-row-label">Hashrate 60DMA</span>
                <span className="m-row-value">
                  {m?.hashrate_sma_60 ? fmtCompact(m.hashrate_sma_60) : '\u2014'}
                </span>
              </div>
              <div className="m-row">
                <span className="m-row-label">Buy signal</span>
                <span
                  className="m-row-value"
                  style={{
                    color:
                      m?.hashribbon_buy_signal === 1
                        ? 'var(--bull)'
                        : 'var(--text2)',
                  }}
                >
                  {m?.hashribbon_buy_signal === 1 ? 'Active' : 'Нет'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Signals ═══ */}
        <div className="metric-group">
          <div className="metric-group-title">Cycle signals</div>
          <div className="signal-grid">
            {(data.signals || []).map((signal, i) => (
              <SignalCard key={`${signal.label}-${i}`} signal={signal} />
            ))}
          </div>
        </div>

        {/* ═══ Chart ═══ */}
        {data.history?.length > 0 && <CycleChart history={data.history} />}

        {/* ═══ Projections ═══ */}
        {data.projections && <ProjectionBlock proj={data.projections} />}

        {/* ═══ Flagged Dates ═══ */}
        {flagged.length > 0 && (
          <div className="metric-group">
            <div className="metric-group-title">Последние flagged даты</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Zone</th>
                    <th>Top</th>
                    <th>Bottom</th>
                    <th>MVRV Z</th>
                    <th>NUPL</th>
                    <th>Puell</th>
                  </tr>
                </thead>
                <tbody>
                  {flagged.map(p => (
                    <tr key={p.date}>
                      <td>{fmtDate(p.date)}</td>
                      <td>
                        <span className={`zone-badge ${zoneTone(p.cycle_zone)}`}>
                          {zoneLabel(p.cycle_zone)}
                        </span>
                      </td>
                      <td
                        className={
                          p.top_score >= 0.7
                            ? 'lift-good'
                            : p.top_score >= 0.45
                              ? 'lift-ok'
                              : 'lift-meh'
                        }
                      >
                        {(p.top_score * 100).toFixed(0)}%
                      </td>
                      <td
                        className={
                          p.bottom_score >= 0.7
                            ? 'lift-good'
                            : p.bottom_score >= 0.45
                              ? 'lift-ok'
                              : 'lift-meh'
                        }
                      >
                        {(p.bottom_score * 100).toFixed(0)}%
                      </td>
                      <td>{fmtNum(p.mvrv_zscore, 2)}</td>
                      <td>{fmtNum(p.nupl, 3)}</td>
                      <td>{fmtNum(p.puell_multiple, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
