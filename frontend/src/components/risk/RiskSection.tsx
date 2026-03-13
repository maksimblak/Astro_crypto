import { useMemo } from 'react';
import type { CalendarDay, ScoreScale } from '../../types/api';
import { riskClass } from '../../utils/scores';
import { fmtDate, parseDateOnly, localDateKey } from '../../utils/dates';

interface Props {
  calendar: CalendarDay[];
  referenceDate?: string;
  scoreScale: ScoreScale;
}

export default function RiskSection({ calendar, referenceDate, scoreScale }: Props) {
  const upcoming = useMemo(() => {
    const today = referenceDate || localDateKey();
    let items = calendar.filter(d => d.date >= today && d.score >= scoreScale.hot).slice(0, 24);
    if (!items.length) {
      items = calendar.filter(d => d.date >= today && d.score >= scoreScale.warm).slice(0, 24);
    }
    return { items, today };
  }, [calendar, referenceDate, scoreScale]);

  return (
    <div className="section" id="sectionRisk">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--bear)', boxShadow: 'var(--glow-red)' }} />
          Ближайшие зоны риска
        </div>
      </div>
      <div className="risk-grid">
        {upcoming.items.length === 0 ? (
          <div className="loading" style={{ animation: 'none' }}>
            Нет ближайших дней с повышенным reversal score
          </div>
        ) : (
          upcoming.items.map(d => {
            const cls = riskClass(d.score, scoreScale);
            const todayDate = parseDateOnly(upcoming.today);
            const daysAway = Math.round((parseDateOnly(d.date).getTime() - todayDate.getTime()) / 86400000);
            const details = (d.details || '').split(' | ').filter(s => s.startsWith('+'));

            return (
              <div key={d.date} className={`risk-item ${cls}`}>
                <div className={`risk-badge ${cls}`}>{d.score.toFixed(1)}</div>
                <div className="risk-body">
                  <div className="risk-date">
                    {fmtDate(d.date)}
                    <span className="days-away">
                      {daysAway === 0 ? 'Сегодня' : `через ${daysAway} дн.`}
                    </span>
                  </div>
                  <div className="risk-dir">
                    {d.direction > 0
                      ? <span className="up">{'\u25B2'} Пик</span>
                      : d.direction < 0
                      ? <span className="down">{'\u25BC'} Дно</span>
                      : 'Нейтрально'}
                  </div>
                  <div className="risk-meta">
                    <span className="tag">{'\u263D'} {d.moon_sign}</span>
                    <span className="tag">{d.moon_element}</span>
                    <span className="tag">{'\u2609'} {d.sun_sign || ''}</span>
                    <span className="tag">{d.quarter}</span>
                    {d.retro_planets && <span className="tag">Ретро: {d.retro_planets}</span>}
                    {d.station_planets && <span className="tag">Станция: {d.station_planets}</span>}
                  </div>
                  {details.length > 0 && (
                    <div className="risk-details">
                      {details.map((line, i) => (
                        <div key={i}>{line}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
