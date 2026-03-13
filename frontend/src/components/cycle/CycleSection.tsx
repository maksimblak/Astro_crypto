import type { CycleData, CycleHistory } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { fmtUsd, stressTone } from '../../utils/format';
import SignalCard from '../regime/SignalCard';
import CycleChart from './CycleChart';

interface Props {
  data: CycleData;
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

export default function CycleSection({ data }: Props) {
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
