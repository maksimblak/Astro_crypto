import { useState, useMemo } from 'react';
import type { CalendarDay, ScoreScale } from '../../types/api';
import { monthLabel } from '../../utils/dates';
import CalendarChart from './CalendarChart';

interface Props {
  data: CalendarDay[];
  scoreScale: ScoreScale;
}

export default function CalendarSection({ data, scoreScale }: Props) {
  const [filterMonth, setFilterMonth] = useState<string | null>(null);

  const months = useMemo(
    () => [...new Set(data.map(d => d.date.substring(0, 7)))].sort(),
    [data]
  );

  const filtered = useMemo(
    () => filterMonth ? data.filter(d => d.date.substring(0, 7) === filterMonth) : data,
    [data, filterMonth]
  );

  return (
    <div className="section" id="sectionCalendar">
      <div className="section-head">
        <div className="section-title"><span className="dot" /> Астро-календарь</div>
        <div className="pill-group">
          <button
            className={`pill ${!filterMonth ? 'active' : ''}`}
            onClick={() => setFilterMonth(null)}
          >
            Все
          </button>
          {months.map(m => (
            <button
              key={m}
              className={`pill ${filterMonth === m ? 'active' : ''}`}
              onClick={() => setFilterMonth(m)}
            >
              {monthLabel(m)}
            </button>
          ))}
        </div>
      </div>
      <div className="card">
        <CalendarChart data={filtered} scoreScale={scoreScale} />
      </div>
    </div>
  );
}
