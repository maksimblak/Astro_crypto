import { useEffect } from 'react';
import TopBar from './components/layout/TopBar';
import HeroSection from './components/hero/HeroSection';
import CalendarSection from './components/calendar/CalendarSection';
import PriceChart from './components/price/PriceChart';
import RegimeSection from './components/regime/RegimeSection';
import RiskSection from './components/risk/RiskSection';
import StatsSection from './components/stats/StatsSection';
import { useToday, useCalendar, useDaily, usePivots, useStats, useRegime } from './hooks/useDashboardData';
import { setScoreThresholds } from './utils/scores';
import { localDateKey } from './utils/dates';

export default function App() {
  const today = useToday();
  const calendar = useCalendar();
  const daily = useDaily();
  const pivots = usePivots();
  const stats = useStats();
  const regime = useRegime();

  useEffect(() => {
    if (stats.data?.score_scale) {
      setScoreThresholds(stats.data.score_scale);
    }
  }, [stats.data]);

  const referenceDate = today.data?.date || localDateKey();
  const isLoading = today.isLoading && calendar.isLoading;

  return (
    <>
      <TopBar />
      <div className="container">
        {isLoading ? (
          <div className="loading">Загрузка данных</div>
        ) : (
          <>
            {today.data && <HeroSection data={today.data} />}
            {calendar.data && <CalendarSection data={calendar.data} />}
            {daily.data && pivots.data && <PriceChart daily={daily.data} pivots={pivots.data} />}
            {regime.data && <RegimeSection data={regime.data} />}
            {calendar.data && <RiskSection calendar={calendar.data} referenceDate={referenceDate} />}
            {stats.data && <StatsSection data={stats.data} />}
          </>
        )}
        <div className="footer">
          AstroBTC Сканер разворотов &middot; Астро-исследование на данных
        </div>
      </div>
    </>
  );
}
