import type { TodayData } from '../../types/api';
import { scoreClass } from '../../utils/scores';
import { fmtDate } from '../../utils/dates';

interface Props {
  data: TodayData;
}

export default function HeroSection({ data }: Props) {
  const sc = data.score || 0;
  const cls = scoreClass(sc);

  const dirText = data.direction > 0
    ? '\u25B2 Склонность к пику'
    : data.direction < 0
    ? '\u25BC Склонность к дну'
    : '\u2594 Нейтрально';

  return (
    <div className="hero">
      <div className="hero-main">
        <div className="hero-label">
          <span className="live-dot" /> Балл разворота сегодня
        </div>
        <div className={`hero-score ${cls}`}>{sc.toFixed(1)}</div>
        <div className="hero-sub">{fmtDate(data.date)} &middot; {dirText}</div>
      </div>
      <div className="hero-cards">
        <div className="hero-card">
          <div className="hc-label">Направление</div>
          <div className={`hc-val ${data.direction > 0 ? 'dir-up' : data.direction < 0 ? 'dir-down' : 'dir-neutral'}`}>
            {data.direction > 0 ? '\u25B2 Пик' : data.direction < 0 ? '\u25BC Дно' : '\u2594 Нейтр.'}
          </div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Знак Луны</div>
          <div className="hc-val">{data.moon_sign || '\u2014'}</div>
          <div className="hc-sub">{data.moon_element || ''}</div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Знак Солнца</div>
          <div className="hc-val">{data.sun_sign || '\u2014'}</div>
          <div className="hc-sub">{data.sun_element || ''}</div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Фаза</div>
          <div className="hc-val" style={{ fontSize: 16 }}>{data.quarter || '\u2014'}</div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Напряжение / Гармония</div>
          <div className="hc-val" style={{ fontSize: 18 }}>{data.tension || 0} / {data.harmony || 0}</div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Затмение</div>
          <div className="hc-val" style={{ fontSize: 18 }}>{data.eclipse_days} дн.</div>
          <div className="hc-sub">{data.eclipse_days <= 7 ? 'Рядом затмение!' : 'Затмений рядом нет'}</div>
        </div>
        <div className="hero-card">
          <div className="hc-label">Ретро планеты</div>
          <div className="hc-val" style={{ fontSize: 14 }}>{data.retro_planets || 'Нет'}</div>
          {data.station_planets && <div className="hc-sub">Станция: {data.station_planets}</div>}
        </div>
      </div>
    </div>
  );
}
