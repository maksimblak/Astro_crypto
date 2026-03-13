import TopBar from './components/layout/TopBar';
import HeroSection from './components/hero/HeroSection';
import CalendarSection from './components/calendar/CalendarSection';
import PriceChart from './components/price/PriceChart';
import CycleSection from './components/cycle/CycleSection';
import RegimeSection from './components/regime/RegimeSection';
import RiskSection from './components/risk/RiskSection';
import StatsSection from './components/stats/StatsSection';
import BacktestSection from './components/backtest/BacktestSection';
import { useToday, useCalendar, useDaily, usePivots, useStats, useRegime, useCycle } from './hooks/useDashboardData';
import { normalizeScoreScale } from './utils/scores';
import { localDateKey } from './utils/dates';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  useWebSocket();
  const today = useToday();
  const calendar = useCalendar();
  const daily = useDaily();
  const pivots = usePivots();
  const stats = useStats();
  const regime = useRegime();
  const cycle = useCycle();
  const scoreScale = normalizeScoreScale(stats.data?.score_scale);

  const referenceDate = today.data?.date || localDateKey();
  const isLoading = today.isLoading || calendar.isLoading;

  return (
    <>
      <TopBar />
      <div className="container">
        {isLoading ? (
          <div className="loading">Загрузка данных</div>
        ) : (
          <>
            {today.data && <HeroSection data={today.data} scoreScale={scoreScale} />}
            {calendar.data && <CalendarSection data={calendar.data} scoreScale={scoreScale} />}
            {daily.data && pivots.data && <PriceChart daily={daily.data} pivots={pivots.data} />}
            {!cycle.isLoading && (
              <CycleSection
                data={cycle.data}
                error={cycle.error instanceof Error ? cycle.error.message : undefined}
              />
            )}
            {regime.data && <RegimeSection data={regime.data} />}
            {calendar.data && (
              <RiskSection
                calendar={calendar.data}
                referenceDate={referenceDate}
                scoreScale={scoreScale}
              />
            )}
            {stats.data && <StatsSection data={stats.data} />}
            <BacktestSection />
          </>
        )}
        <div className="footer">
          AstroBTC Сканер разворотов &middot; Астро-исследование на данных
        </div>
      </div>
    </>
  );
}
