import type { CycleData, CycleHistory, CycleProjections } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { fmtUsd, stressTone } from '../../utils/format';
import SignalCard from '../regime/SignalCard';
import CycleChart from './CycleChart';

interface Props {
  data?: CycleData;
  error?: string;
}

function zoneLabel(zone: string): string {
  if (zone === 'top_zone') return 'Top zone';
  if (zone === 'top_watch') return 'Top watch';
  if (zone === 'bottom_zone') return 'Bottom zone';
  if (zone === 'bottom_watch') return 'Bottom watch';
  if (zone === 'mixed') return 'Mixed';
  return 'Neutral';
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

function flaggedRows(history: CycleHistory[]): CycleHistory[] {
  return history
    .filter(point => point.top_score >= 0.45 || point.bottom_score >= 0.45 || point.pi_cycle_signal === 1 || point.hashribbon_buy_signal === 1)
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

function ProjectionBlock({ proj }: { proj: CycleProjections }) {
  const pl = proj.power_law;
  const gr = proj.golden_ratio;
  const ht = proj.halving_timing;
  const dr = proj.diminishing_returns;
  const comp = proj.composite;

  return (
    <>
      <div className="signal-section-title">Cycle Projections</div>

      {/* Composite forecast summary */}
      <div className="projection-summary">
        <div className="projection-card highlight">
          <div className="label">Прогноз пика</div>
          <div className="value">{fmtDate(comp.projected_peak_date)}</div>
          <div className="sub">
            {comp.days_to_peak > 0
              ? `Через ${comp.days_to_peak} дней`
              : comp.days_to_peak === 0
                ? 'Сегодня'
                : `${Math.abs(comp.days_to_peak)} дней назад`}
          </div>
        </div>
        <div className="projection-card highlight">
          <div className="label">Median target</div>
          <div className="value">{comp.median_target ? fmtUsd(comp.median_target) : '\u2014'}</div>
          <div className="sub">
            {comp.price_targets.length > 0 &&
              `${fmtUsd(comp.price_targets[0])} \u2013 ${fmtUsd(comp.price_targets[comp.price_targets.length - 1])}`}
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

      {/* Model details grid */}
      <div className="signal-section-title" style={{ marginTop: '1.2rem' }}>Модели</div>
      <div className="signal-grid">
        {/* Power Law */}
        <div className={`signal-card ${plPositionTone(pl.position)}`}>
          <div className="signal-label">POWER LAW</div>
          <div className="signal-value">{fmtUsd(pl.fair_value)}</div>
          <div className="signal-note">
            Fair value (R²={pl.r_squared.toFixed(2)}).
            Текущая позиция: {(pl.position * 100).toFixed(0)}% — {plPositionLabel(pl.position)}.
            Коридор ±1σ: {fmtUsd(pl.band_1sigma[0])} – {fmtUsd(pl.band_1sigma[1])}.
            На дату пика: fair {fmtUsd(pl.fair_at_projected_peak)}, потолок {fmtUsd(pl.band_at_projected_peak[1])}.
          </div>
        </div>

        {/* Golden Ratio */}
        <div className="signal-card neutral">
          <div className="signal-label">GOLDEN RATIO MULTIPLIER</div>
          <div className="signal-value">{fmtUsd(gr.current_ceiling.projected_ceiling)}</div>
          <div className="signal-note">
            350DMA = {fmtUsd(gr.sma350)}.
            Текущий ceiling: ×{gr.current_ceiling.fib_level} = {fmtUsd(gr.current_ceiling.projected_ceiling)}.
            Следующий цикл: ×{gr.current_ceiling.next_cycle_fib} = {fmtUsd(gr.current_ceiling.next_cycle_ceiling)}.
          </div>
        </div>

        {/* Halving Timing */}
        <div className="signal-card neutral">
          <div className="signal-label">HALVING TIMING</div>
          <div className="signal-value">{fmtDate(ht.projected_peak)}</div>
          <div className="signal-note">
            Последний халвинг: {fmtDate(ht.last_halving)}.
            Среднее от халвинга до пика: {ht.halving_model?.avg_days ?? '\u2014'}д (последние 3 цикла).
            Окно: {fmtDate(ht.peak_window_early)} – {fmtDate(ht.peak_window_late)}.
            Следующий халвинг ~{fmtDate(ht.next_halving_est)}.
          </div>
        </div>

        {/* Diminishing Returns */}
        <div className="signal-card neutral">
          <div className="signal-label">DIMINISHING RETURNS</div>
          <div className="signal-value">{fmtUsd(dr.projected_peak_from_bottom)}</div>
          <div className="signal-note">
            Decay factor: ×{dr.avg_decay} между циклами.
            Прогноз ROI: {dr.projected_next_roi_x}× (конс. {dr.projected_next_roi_conservative_x}×).
            Пик: {fmtUsd(dr.projected_peak_conservative)} – {fmtUsd(dr.projected_peak_from_bottom)}.
            Медвежья просадка: ~{dr.projected_next_drawdown_pct}% → дно ~{fmtUsd(dr.projected_next_bottom)}.
          </div>
        </div>

        {/* Mayer Multiple */}
        <div className={`signal-card ${
          proj.mayer_multiple != null && proj.mayer_multiple > 2.4 ? 'bear' :
          proj.mayer_multiple != null && proj.mayer_multiple < 0.8 ? 'bull' : 'neutral'
        }`}>
          <div className="signal-label">MAYER MULTIPLE</div>
          <div className="signal-value">{proj.mayer_multiple != null ? proj.mayer_multiple.toFixed(2) : '\u2014'}</div>
          <div className="signal-note">
            Price / 200DMA ({fmtUsd(proj.sma200)}).
            Исторически: top &gt; 2.4, bottom &lt; 0.5.
          </div>
        </div>

        {/* Pi Cycle Distance */}
        <div className={`signal-card ${
          proj.pi_cycle_distance != null && proj.pi_cycle_distance > -0.02 ? 'bear' : 'neutral'
        }`}>
          <div className="signal-label">PI CYCLE DISTANCE</div>
          <div className="signal-value">{proj.pi_cycle_distance != null ? (proj.pi_cycle_distance * 100).toFixed(1) + '%' : '\u2014'}</div>
          <div className="signal-note">
            Расстояние 111DMA до 2×350DMA.
            0% = пересечение (top signal). Сейчас {proj.pi_cycle_distance != null && proj.pi_cycle_distance < 0 ? 'ниже' : 'выше'}.
          </div>
        </div>
      </div>

      {/* ROI History Table */}
      {dr.cycle_rois.length > 0 && (
        <>
          <div className="signal-section-title" style={{ marginTop: '1.2rem' }}>ROI по циклам</div>
          <table>
            <thead>
              <tr>
                <th>Цикл</th>
                <th>Дно</th>
                <th>Пик</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody>
              {dr.cycle_rois.map(r => (
                <tr key={r.cycle}>
                  <td>{r.cycle}</td>
                  <td>{fmtUsd(r.bottom)}</td>
                  <td>{fmtUsd(r.top)}</td>
                  <td className="lift-good">{r.roi_x}×</td>
                </tr>
              ))}
              <tr style={{ opacity: 0.7, fontStyle: 'italic' }}>
                <td>Next</td>
                <td>{fmtUsd(dr.projected_next_bottom)}</td>
                <td>{fmtUsd(dr.projected_peak_conservative)} – {fmtUsd(dr.projected_peak_from_bottom)}</td>
                <td>{dr.projected_next_roi_conservative_x}× – {dr.projected_next_roi_x}×</td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

export default function CycleSection({ data, error }: Props) {
  if (error || !data) {
    return (
      <div className="section" id="sectionCycle">
        <div className="section-head">
          <div className="section-title">
            <span className="dot" style={{ background: 'var(--bear)', boxShadow: 'var(--glow-red)' }} />
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
  const toneClass = stressTone(tone);
  const flagged = flaggedRows(data.history || []);

  const metrics = [
    { label: 'BTC', value: fmtUsd(data.price), sub: `на ${fmtDate(data.as_of)}` },
    { label: 'Top score', value: `${(data.top_score * 100).toFixed(1)}%`, sub: 'Composite риск перегрева' },
    { label: 'Bottom score', value: `${(data.bottom_score * 100).toFixed(1)}%`, sub: 'Composite вероятность дна' },
    { label: 'Bias', value: `${data.cycle_bias > 0 ? '+' : ''}${(data.cycle_bias * 100).toFixed(1)}%`, sub: 'Top score минус bottom score' },
    { label: 'MVRV Z', value: fmtNum(data.metrics?.mvrv_zscore, 2), sub: `top>${fmtNum(data.metrics?.mvrv_top_threshold, 2)} / bottom<${fmtNum(data.metrics?.mvrv_bottom_extreme, 2)}` },
    { label: 'NUPL', value: fmtNum(data.metrics?.nupl, 3), sub: `top>${fmtNum(data.metrics?.nupl_top_threshold, 3)} / bottom<${fmtNum(data.metrics?.nupl_bottom_extreme, 3)}` },
    { label: 'Puell', value: fmtNum(data.metrics?.puell_multiple, 3), sub: `top>${fmtNum(data.metrics?.puell_top_threshold, 2)} / bottom<${fmtNum(data.metrics?.puell_bottom_extreme, 2)}` },
    { label: 'Pi signal', value: `${data.metrics?.pi_cycle_signal ?? 0}`, sub: '1 = top crossover, -1 = down-cross' },
    { label: 'Pi 111DMA', value: fmtUsd(data.metrics?.pi_sma111 ?? undefined), sub: 'Короткая MA из Pi Cycle' },
    { label: 'Pi 350DMA×2', value: fmtUsd(data.metrics?.pi_sma350x2 ?? undefined), sub: 'Длинная MA из Pi Cycle' },
    { label: 'Hash trend', value: data.metrics?.hashribbon_trend || '\u2014', sub: 'Состояние hash ribbons' },
    { label: 'Hash buy', value: `${data.metrics?.hashribbon_buy_signal ?? 0}`, sub: '1 = свежий buy-confirmation' },
  ];

  return (
    <div className="section" id="sectionCycle">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--bear)', boxShadow: 'var(--glow-red)' }} />
          Пики и дно BTC
        </div>
      </div>
      <div className="card">
        <div className="cycle-overview">
          <div className={`cycle-main ${toneClass}`}>
            <div className="cycle-kicker">Macro cycle layer на {fmtDate(data.as_of)}</div>
            <div className="cycle-title">{data.cycle_label}</div>
            <div className="cycle-copy">{data.summary}</div>
            <div className="cycle-score-row">
              <div className="cycle-score-block top">
                <div className="cycle-score-label">Top</div>
                <div className="cycle-score-value">{(data.top_score * 100).toFixed(0)}%</div>
              </div>
              <div className="cycle-score-block bottom">
                <div className="cycle-score-label">Bottom</div>
                <div className="cycle-score-value">{(data.bottom_score * 100).toFixed(0)}%</div>
              </div>
            </div>
            <div className="regime-chips">
              <span className={`regime-chip ${toneClass}`}>{zoneLabel(data.cycle_zone)}</span>
              <span className="regime-chip neutral">{fmtUsd(data.price)}</span>
              <span className={`regime-chip ${data.cycle_bias >= 0 ? 'bear' : 'bull'}`}>
                Bias {data.cycle_bias > 0 ? '+' : ''}{(data.cycle_bias * 100).toFixed(1)}%
              </span>
            </div>
          </div>
          <div className="cycle-metrics">
            {metrics.map(metric => (
              <div key={metric.label} className="regime-metric">
                <div className="label">{metric.label}</div>
                <div className="value">{metric.value}</div>
                <div className="sub">{metric.sub}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="signal-section-title">Cycle signals</div>
        <div className="signal-grid">
          {(data.signals || []).map((signal, index) => (
            <SignalCard key={`${signal.label}-${index}`} signal={signal} />
          ))}
        </div>

        {data.history?.length > 0 && <CycleChart history={data.history} />}

        {data.projections && <ProjectionBlock proj={data.projections} />}

        {flagged.length > 0 && (
          <>
            <div className="signal-section-title">Последние flagged даты</div>
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
                {flagged.map(point => (
                  <tr key={point.date}>
                    <td>{fmtDate(point.date)}</td>
                    <td>{zoneLabel(point.cycle_zone)}</td>
                    <td className={point.top_score >= 0.7 ? 'lift-good' : point.top_score >= 0.45 ? 'lift-ok' : 'lift-meh'}>
                      {(point.top_score * 100).toFixed(0)}%
                    </td>
                    <td className={point.bottom_score >= 0.7 ? 'lift-good' : point.bottom_score >= 0.45 ? 'lift-ok' : 'lift-meh'}>
                      {(point.bottom_score * 100).toFixed(0)}%
                    </td>
                    <td>{fmtNum(point.mvrv_zscore, 2)}</td>
                    <td>{fmtNum(point.nupl, 3)}</td>
                    <td>{fmtNum(point.puell_multiple, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
