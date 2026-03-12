import type { StatsData } from '../../types/api';
import { fmtDate } from '../../utils/dates';

interface Props {
  data: StatsData;
}

export default function StatsSection({ data }: Props) {
  const periodText = data.period_start && data.period_end
    ? `${fmtDate(data.period_start)} - ${fmtDate(data.period_end)}`
    : 'Период не указан';

  return (
    <div className="section" id="sectionStats">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--neon-purple)', boxShadow: '0 0 20px rgba(139,92,246,0.3)' }} />
          Эффективность модели
        </div>
      </div>
      <div className="card">
        <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.8px' }}>
          Holdout-валидация: {periodText}
        </div>
        <div className="stats-row">
          <div className="stat-block">
            <div className="stat-val">{data.baseline_avg_score}</div>
            <div className="stat-label">Ср. балл (holdout дни)</div>
          </div>
          <div className="stat-block">
            <div className="stat-val accent-green">{data.pivot_avg_score}</div>
            <div className="stat-label">Ср. балл (holdout развороты)</div>
          </div>
          <div className="stat-block">
            <div className="stat-val accent-yellow">{data.total_pivots}</div>
            <div className="stat-label">Разворотов в holdout</div>
          </div>
          <div className="stat-block">
            <div className="stat-val">{data.direction_accuracy}%</div>
            <div className="stat-label">Точность направления</div>
          </div>
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text2)' }}>
          Анализ порогов
        </div>
        <table>
          <thead>
            <tr>
              <th>Порог</th>
              <th>Дней в holdout</th>
              <th>Поймано разворотов</th>
              <th>Lift</th>
            </tr>
          </thead>
          <tbody>
            {data.thresholds.map(t => {
              const cls = t.lift >= 2 ? 'lift-good' : t.lift >= 1.2 ? 'lift-ok' : 'lift-meh';
              return (
                <tr key={t.threshold}>
                  <td style={{ fontFamily: 'JetBrains Mono' }}>&ge; {Number(t.threshold).toFixed(1)}</td>
                  <td>{t.days_count} <span style={{ color: 'var(--text2)' }}>({t.days_pct}%)</span></td>
                  <td>{t.pivots_in_zone}</td>
                  <td className={cls}>{t.lift}x</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
