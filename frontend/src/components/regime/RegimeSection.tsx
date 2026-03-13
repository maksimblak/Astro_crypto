import type { RegimeData } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { fmtUsd, regimeTone, stressTone } from '../../utils/format';
import SignalCard from './SignalCard';
import RegimeChart from './RegimeChart';

interface Props {
  data: RegimeData;
}

export default function RegimeSection({ data }: Props) {
  const tone = regimeTone(data.regime_code);
  const stressChipTone = stressTone(data.stress_tone);
  const contextChipTone = stressTone(data.context_tone);
  const setupTone = stressTone(data.setup_tone);
  const oiStateLabel = data.metrics?.oi_price_state_1d === 'long_build' ? 'Long build'
    : data.metrics?.oi_price_state_1d === 'short_build' ? 'Short build'
    : data.metrics?.oi_price_state_1d === 'short_cover' ? 'Short cover'
    : data.metrics?.oi_price_state_1d === 'long_unwind' ? 'Long unwind'
    : '\u2014';
  const biasLabel = data.bias === 'risk-on' ? 'Risk-on'
    : data.bias === 'risk-off' ? 'Risk-off'
    : 'Нейтрально';

  const m = data.metrics || {};
  const metrics = [
    { label: 'BTC', value: fmtUsd(data.price), sub: `на ${fmtDate(data.as_of)}` },
    { label: 'Confidence', value: `${data.confidence}%`, sub: 'Сколько условий режима сейчас совпало' },
    { label: 'Direction score', value: `${data.direction_score > 0 ? '+' : ''}${data.direction_score}`, sub: 'Чистый directional score без stress-компоненты' },
    { label: 'Stress score', value: `${data.stress_score}`, sub: 'Отдельный слой турбулентности рынка' },
    { label: 'Context score', value: `${data.context_score > 0 ? '+' : ''}${data.context_score}`, sub: 'Attention, derivatives и on-chain как отдельный overlay' },
    { label: 'Momentum 90д', value: `${m.momentum_90 ?? '\u2014'}%`, sub: 'Среднесрочный импульс' },
    { label: 'Цена vs 200DMA', value: `${m.close_vs_200 ?? '\u2014'}%`, sub: 'Главный structural filter режима' },
    { label: 'Amihud z', value: `${m.amihud_z_90d ?? '\u2014'}`, sub: 'Liquidity stress vs trailing 90д baseline' },
    { label: 'Range state', value: `${m.range_compression_20d ?? '\u2014'}x`, sub: 'Текущий диапазон vs median 20д' },
    { label: 'Просадка от ATH', value: `${m.drawdown_ath ?? '\u2014'}%`, sub: 'Насколько далеко рынок от пика' },
    { label: 'Wikipedia z', value: `${m.wiki_views_z_30d ?? '\u2014'}`, sub: 'Внешнее внимание к BTC vs 30д baseline' },
    { label: 'Fear & Greed', value: `${m.fear_greed_value ?? '\u2014'}`, sub: 'Сантимент толпы по шкале 0-100' },
    { label: 'Funding z', value: `${m.funding_rate_z_30d ?? '\u2014'}`, sub: 'Watchlist only: в context score пока не входит' },
    { label: 'Funding divergence 3д', value: `${m.funding_price_divergence_3d ?? '\u2014'}`, sub: 'Положительное = price и funding расходятся' },
    { label: 'Perp premium', value: `${m.perp_premium_daily ?? '\u2014'}%`, sub: 'Премия perpetual к spot/index' },
    { label: 'OI delta 1д', value: `${m.open_interest_delta_1d ?? '\u2014'}%`, sub: 'Дневное изменение открытого интереса' },
    { label: 'OI delta z', value: `${m.open_interest_delta_z_30d ?? '\u2014'}`, sub: 'Насколько необычно текущее изменение OI' },
    { label: 'OI state', value: oiStateLabel, sub: 'Long build / short build / unwind / cover' },
    { label: 'OI z', value: `${m.open_interest_z_30d ?? '\u2014'}`, sub: 'Насколько раздут открытый интерес' },
    { label: 'DXY 20д', value: `${m.dxy_return_20d ?? '\u2014'}%`, sub: 'Сильный рост доллара = macro headwind' },
    { label: 'DXY z', value: `${m.dxy_return_z_90d ?? '\u2014'}`, sub: 'Насколько необычен импульс доллара' },
    { label: 'US10Y 20д', value: `${m.us10y_change_20d_bps ?? '\u2014'} bps`, sub: 'Изменение доходности 10-леток за 20 дней' },
    { label: 'US10Y z', value: `${m.us10y_change_z_90d ?? '\u2014'}`, sub: 'Насколько необычен rates shock' },
    { label: 'BTC/SPX corr', value: `${m.btc_spx_corr_30d ?? '\u2014'}`, sub: 'Высокая корреляция = macro доминирует' },
    { label: 'Active addr z', value: `${m.unique_addresses_z_30d ?? '\u2014'}`, sub: 'Сильнейший on-chain сигнал по backtest' },
  ];

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

  return (
    <div className="section" id="sectionRegime">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--bull)', boxShadow: 'var(--glow-green)' }} />
          Рыночный режим
        </div>
      </div>
      <div className="card">
        {/* Setup banner */}
        <div className="setup-banner">
          <div className={`setup-score ${setupTone}`}>
            {data.setup_score > 0 ? '+' : ''}{data.setup_score}
          </div>
          <div className="setup-copy">
            <div className="setup-kicker">Сводный индикаторный score на день</div>
            <div className="setup-label">{data.setup_label}</div>
            <div className="setup-text">
              {data.setup_summary} Это не прогноз цены в процентах, а быстрая сводка того, насколько хорошо текущие индикаторы складываются в дневной setup.
            </div>
          </div>
        </div>

        {/* Regime overview */}
        <div className="regime-overview">
          <div className="regime-main">
            <div className="regime-kicker">Режим на {fmtDate(data.as_of)}</div>
            <div className="regime-title">{data.regime_label}</div>
            <div className="regime-copy">{data.summary}</div>
            <div className="regime-chips">
              <span className={`regime-chip ${tone}`}>{biasLabel}</span>
              <span className={`regime-chip ${stressChipTone}`}>{data.stress_label}</span>
              <span className={`regime-chip ${contextChipTone}`}>{data.context_label}</span>
              <span className={`regime-chip ${tone}`}>{data.confidence}% confidence</span>
            </div>
          </div>
          <div className="regime-metrics">
            {metrics.map(met => (
              <div key={met.label} className="regime-metric">
                <div className="label">{met.label}</div>
                <div className="value">{met.value}</div>
                <div className="sub">{met.sub}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Signals */}
        <div className="signal-section-title">Direction signals</div>
        <div className="signal-grid">
          {(data.direction_signals || []).map((s, i) => <SignalCard key={i} signal={s} />)}
        </div>
        <div className="signal-section-title">Stress signals</div>
        <div className="signal-grid">
          {(data.stress_signals || []).map((s, i) => <SignalCard key={i} signal={s} />)}
        </div>
        <div className="signal-section-title">External context</div>
        <div className="signal-grid">
          {(data.context_signals || []).map((s, i) => <SignalCard key={i} signal={s} />)}
        </div>

        {/* Chart */}
        {data.history?.length > 0 && <RegimeChart history={data.history} />}
      </div>
    </div>
  );
}
