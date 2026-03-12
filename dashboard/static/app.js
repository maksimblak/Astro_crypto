/* AstroBTC Dashboard — main application script */

const MO_RU = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const MO_RU_FULL = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];

function parseDateOnly(value) {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}
function fmtDate(d) {
  const dt = parseDateOnly(d);
  return dt.getDate() + ' ' + MO_RU[dt.getMonth()] + ' ' + dt.getFullYear();
}
function fmtShort(d) {
  const dt = parseDateOnly(d);
  return dt.getDate() + ' ' + MO_RU[dt.getMonth()];
}
function localDateKey(dt = new Date()) {
  const year = dt.getFullYear();
  const month = String(dt.getMonth() + 1).padStart(2, '0');
  const day = String(dt.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
function scrollTo(sel) {
  document.querySelector(sel)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
let scoreThresholds = { cool: 0.5, warm: 1.0, hot: 1.5, extreme: 2.0 };
let dashboardToday = null;

function setScoreThresholds(stats) {
  if (!stats?.score_scale) return;
  scoreThresholds = {
    cool: Number(stats.score_scale.cool) || scoreThresholds.cool,
    warm: Number(stats.score_scale.warm) || scoreThresholds.warm,
    hot: Number(stats.score_scale.hot) || scoreThresholds.hot,
    extreme: Number(stats.score_scale.extreme) || scoreThresholds.extreme,
  };
}

function scoreClass(s) {
  if (s >= scoreThresholds.hot) return 'hot';
  if (s >= scoreThresholds.warm) return 'warm';
  if (s >= scoreThresholds.cool) return 'cool';
  return 'cold';
}
function scoreBarColor(s) {
  if (s >= scoreThresholds.extreme) return 'rgba(255,59,92,0.92)';
  if (s >= scoreThresholds.hot) return 'rgba(255,107,53,0.88)';
  if (s >= scoreThresholds.warm) return 'rgba(245,158,11,0.82)';
  if (s >= scoreThresholds.cool) return 'rgba(0,212,255,0.62)';
  return 'rgba(75,85,99,0.4)';
}
function scoreBarBorder(s) {
  if (s >= scoreThresholds.extreme) return '#ff3b5c';
  if (s >= scoreThresholds.hot) return '#ff6b35';
  if (s >= scoreThresholds.warm) return '#f59e0b';
  if (s >= scoreThresholds.cool) return '#00d4ff';
  return '#4b5563';
}

function riskClass(s) {
  if (s >= scoreThresholds.hot) return 'hot';
  if (s >= scoreThresholds.warm) return 'warm';
  return 'mild';
}

let calendarData = [], calChart = null, regimeChart = null;

function regimeTone(code) {
  if (code === 'bull' || code === 'recovery') return 'bull';
  if (code === 'bear' || code === 'distribution') return 'bear';
  return 'neutral';
}
function stressTone(tone) {
  if (tone === 'bull' || tone === 'bear' || tone === 'neutral') return tone;
  return 'neutral';
}
function fmtUsd(v) {
  if (v == null) return '—';
  return '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
}
function showBlockError(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `<div class="loading" style="animation:none">${message}</div>`;
}

async function init() {
  const [todayR, calR, dailyR, pivotsR, statsR, regimeR] = await Promise.all([
    fetch('/api/today'), fetch('/api/calendar'), fetch('/api/daily'),
    fetch('/api/pivots'), fetch('/api/stats'), fetch('/api/regime')
  ]);
  const today = await todayR.json();
  calendarData = await calR.json();
  const daily = await dailyR.json();
  const pivots = await pivotsR.json();
  const stats = await statsR.json();
  const regime = await regimeR.json();
  setScoreThresholds(stats);
  dashboardToday = today.date || localDateKey();

  if (Array.isArray(calendarData)) {
    buildCalendar(calendarData);
    buildRisk(calendarData, dashboardToday);
  }
  if (today.date) buildHero(today);
  if (Array.isArray(daily) && Array.isArray(pivots)) buildPrice(daily, pivots);
  if (Array.isArray(regime.history)) {
    buildRegime(regime);
  } else if (regime.error) {
    showBlockError('regimeBlock', regime.error);
  }
  if (stats.thresholds) buildStats(stats);
}

function buildHero(t) {
  const sc = t.score || 0;
  const el = document.getElementById('heroScore');
  el.textContent = sc.toFixed(1);
  el.className = 'hero-score ' + scoreClass(sc);

  const dirText = t.direction > 0 ? '&#9650; Склонность к пику' : t.direction < 0 ? '&#9660; Склонность к дну' : '&#9644; Нейтрально';
  document.getElementById('heroSub').innerHTML = `${fmtDate(t.date)} &middot; ${dirText}`;

  document.getElementById('heroCards').innerHTML = `
    <div class="hero-card">
      <div class="hc-label">Направление</div>
      <div class="hc-val ${t.direction > 0 ? 'dir-up' : t.direction < 0 ? 'dir-down' : 'dir-neutral'}">
        ${t.direction > 0 ? '&#9650; Пик' : t.direction < 0 ? '&#9660; Дно' : '&#9644; Нейтр.'}
      </div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Знак Луны</div>
      <div class="hc-val">${t.moon_sign || '—'}</div>
      <div class="hc-sub">${t.moon_element || ''}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Знак Солнца</div>
      <div class="hc-val">${t.sun_sign || '—'}</div>
      <div class="hc-sub">${t.sun_element || ''}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Фаза</div>
      <div class="hc-val" style="font-size:16px">${t.quarter || '—'}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Напряжение / Гармония</div>
      <div class="hc-val" style="font-size:18px">${t.tension || 0} / ${t.harmony || 0}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Затмение</div>
      <div class="hc-val" style="font-size:18px">${t.eclipse_days} дн.</div>
      <div class="hc-sub">${t.eclipse_days <= 7 ? 'Рядом затмение!' : 'Затмений рядом нет'}</div>
    </div>
    <div class="hero-card">
      <div class="hc-label">Ретро планеты</div>
      <div class="hc-val" style="font-size:14px">${t.retro_planets || 'Нет'}</div>
      ${t.station_planets ? '<div class="hc-sub">Станция: '+t.station_planets+'</div>' : ''}
    </div>
  `;
}

function buildCalendar(data, filterMonth) {
  let filtered = filterMonth ? data.filter(d => d.date.substring(0,7) === filterMonth) : data;

  const months = [...new Set(data.map(d => d.date.substring(0,7)))].sort();
  const box = document.getElementById('monthFilters');
  box.innerHTML = `<button class="pill ${!filterMonth?'active':''}" onclick="buildCalendar(calendarData)">Все</button>`;
  months.forEach(m => {
    const dt = parseDateOnly(m + '-01');
    const lbl = MO_RU[dt.getMonth()] + ' ' + dt.getFullYear();
    box.innerHTML += `<button class="pill ${filterMonth===m?'active':''}" onclick="buildCalendar(calendarData,'${m}')">${lbl}</button>`;
  });

  const labels = filtered.map(d => fmtShort(d.date));
  const scores = filtered.map(d => d.score);

  if (calChart) calChart.destroy();

  calChart = new Chart(document.getElementById('calendarChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: scores,
        backgroundColor: scores.map(s => scoreBarColor(s)),
        borderColor: scores.map(s => scoreBarBorder(s)),
        borderWidth: 1, borderRadius: 4, borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17,24,39,0.95)',
          borderColor: 'rgba(0,212,255,0.2)', borderWidth: 1,
          titleColor: '#e8eaed', bodyColor: '#9ca3af',
          titleFont: { size: 13, weight: 600 },
          bodyFont: { size: 12, family: 'JetBrains Mono' },
          padding: 14, cornerRadius: 10,
          callbacks: {
            title: (items) => fmtDate(filtered[items[0].dataIndex].date),
            afterTitle: (items) => {
              const d = filtered[items[0].dataIndex];
              return `${d.quarter} | ☽ ${d.moon_sign} (${d.moon_element}) | ☉ ${d.sun_sign || '—'}`;
            },
            label: (item) => `Балл: ${item.raw.toFixed(1)}`,
            afterBody: (items) => {
              const d = filtered[items[0].dataIndex];
              if (!d.details) return '';
              return '\n' + d.details.split(' | ').join('\n');
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#4b5563', maxRotation: 90, font: { size: filtered.length > 60 ? 7 : 10 } },
          grid: { display: false }
        },
        y: {
          ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 11 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
          beginAtZero: true,
        }
      }
    }
  });
}

function buildPrice(daily, pivots) {
  const highs = pivots.filter(p => p.is_high === 1);
  const lows = pivots.filter(p => p.is_high === 0);

  function pts(arr) {
    return arr.map(p => ({ x: p.date, y: p.price, r: Math.max(4, Math.min(12, (p.tension_count||0)*1.5 + (p.near_eclipse||0)*3)) }));
  }

  new Chart(document.getElementById('priceChart').getContext('2d'), {
    type: 'line',
    data: {
      labels: daily.map(d => d.date),
      datasets: [
        {
          label: 'BTC',
          data: daily.map(d => d.close),
          borderColor: 'rgba(59,130,246,0.8)',
          backgroundColor: ctx => {
            const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
            g.addColorStop(0, 'rgba(59,130,246,0.15)');
            g.addColorStop(1, 'rgba(59,130,246,0)');
            return g;
          },
          borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.1, order: 2,
        },
        {
          label: 'Пики', type: 'bubble', data: pts(highs),
          backgroundColor: 'rgba(255,59,92,0.6)', borderColor: '#ff3b5c', borderWidth: 1.5, order: 1,
        },
        {
          label: 'Дно', type: 'bubble', data: pts(lows),
          backgroundColor: 'rgba(0,255,136,0.5)', borderColor: '#00ff88', borderWidth: 1.5, order: 1,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#9ca3af', font: { size: 12 }, usePointStyle: true, pointStyle: 'circle' }
        },
        tooltip: {
          backgroundColor: 'rgba(17,24,39,0.95)',
          borderColor: 'rgba(59,130,246,0.2)', borderWidth: 1,
          titleColor: '#e8eaed', bodyColor: '#9ca3af',
          padding: 12, cornerRadius: 10,
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.type === 'bubble') {
                return `${ctx.dataset.label}: $${ctx.raw.y.toLocaleString()} (${ctx.raw.x})`;
              }
              return `BTC: $${ctx.parsed.y.toLocaleString()}`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#4b5563', maxTicksLimit: 20,
            callback: function(v) { const d = this.getLabelForValue(v); return d ? d.substring(0,7) : ''; }
          },
          grid: { display: false }
        },
        y: {
          type: 'logarithmic',
          ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 11 },
            callback: v => '$' + (v>=1000 ? (v/1000).toFixed(0)+'k' : v)
          },
          grid: { color: 'rgba(255,255,255,0.04)' },
        }
      }
    }
  });
}

function buildRegime(r) {
  const tone = regimeTone(r.regime_code);
  const stressChipTone = stressTone(r.stress_tone);
  const contextChipTone = stressTone(r.context_tone);
  const setupTone = stressTone(r.setup_tone);
  const biasLabel = r.bias === 'risk-on' ? 'Risk-on'
                  : r.bias === 'risk-off' ? 'Risk-off'
                  : 'Нейтрально';
  const history = r.history || [];
  const block = document.getElementById('regimeBlock');

  const metrics = [
    { label: 'BTC', value: fmtUsd(r.price), sub: `на ${fmtDate(r.as_of)}` },
    { label: 'Confidence', value: `${r.confidence}%`, sub: 'Сколько условий режима сейчас совпало' },
    { label: 'Direction score', value: `${r.direction_score > 0 ? '+' : ''}${r.direction_score}`, sub: 'Чистый directional score без stress-компоненты' },
    { label: 'Stress score', value: `${r.stress_score}`, sub: 'Отдельный слой турбулентности рынка' },
    { label: 'Context score', value: `${r.context_score > 0 ? '+' : ''}${r.context_score}`, sub: 'Attention, derivatives и on-chain как отдельный overlay' },
    { label: 'Momentum 90д', value: `${r.metrics?.momentum_90 ?? '—'}%`, sub: 'Среднесрочный импульс' },
    { label: 'Цена vs 200DMA', value: `${r.metrics?.close_vs_200 ?? '—'}%`, sub: 'Главный structural filter режима' },
    { label: 'Amihud z', value: `${r.metrics?.amihud_z_90d ?? '—'}`, sub: 'Liquidity stress vs trailing 90д baseline' },
    { label: 'Range state', value: `${r.metrics?.range_compression_20d ?? '—'}x`, sub: 'Текущий диапазон vs median 20д' },
    { label: 'Просадка от ATH', value: `${r.metrics?.drawdown_ath ?? '—'}%`, sub: 'Насколько далеко рынок от пика' },
    { label: 'Wikipedia z', value: `${r.metrics?.wiki_views_z_30d ?? '—'}`, sub: 'Внешнее внимание к BTC vs 30д baseline' },
    { label: 'Fear & Greed', value: `${r.metrics?.fear_greed_value ?? '—'}`, sub: 'Сантимент толпы по шкале 0-100' },
    { label: 'Funding z', value: `${r.metrics?.funding_rate_z_30d ?? '—'}`, sub: 'Watchlist only: в context score пока не входит' },
    { label: 'Perp premium', value: `${r.metrics?.perp_premium_daily ?? '—'}%`, sub: 'Премия perpetual к spot/index' },
    { label: 'OI z', value: `${r.metrics?.open_interest_z_30d ?? '—'}`, sub: 'Насколько раздут открытый интерес' },
    { label: 'Active addr z', value: `${r.metrics?.unique_addresses_z_30d ?? '—'}`, sub: 'Сильнейший on-chain сигнал по backtest' },
  ];

  const directionSignalsHtml = (r.direction_signals || []).map(s => `
    <div class="signal-card ${s.tone}">
      <div class="signal-label">${s.label}</div>
      <div class="signal-value ${s.tone}">${s.value}</div>
      <div class="signal-note">${s.note}</div>
    </div>
  `).join('');
  const stressSignalsHtml = (r.stress_signals || []).map(s => `
    <div class="signal-card ${s.tone}">
      <div class="signal-label">${s.label}</div>
      <div class="signal-value ${s.tone}">${s.value}</div>
      <div class="signal-note">${s.note}</div>
    </div>
  `).join('');
  const contextSignalsHtml = (r.context_signals || []).map(s => `
    <div class="signal-card ${s.tone}">
      <div class="signal-label">${s.label}</div>
      <div class="signal-value ${s.tone}">${s.value}</div>
      <div class="signal-note">${s.note}</div>
    </div>
  `).join('');

  block.innerHTML = `
    <div class="setup-banner">
      <div class="setup-score ${setupTone}">${r.setup_score > 0 ? '+' : ''}${r.setup_score}</div>
      <div class="setup-copy">
        <div class="setup-kicker">Сводный индикаторный score на день</div>
        <div class="setup-label">${r.setup_label}</div>
        <div class="setup-text">${r.setup_summary} Это не прогноз цены в процентах, а быстрая сводка того, насколько хорошо текущие индикаторы складываются в дневной setup.</div>
      </div>
    </div>
    <div class="regime-overview">
      <div class="regime-main">
        <div class="regime-kicker">Режим на ${fmtDate(r.as_of)}</div>
        <div class="regime-title">${r.regime_label}</div>
        <div class="regime-copy">${r.summary}</div>
        <div class="regime-chips">
          <span class="regime-chip ${tone}">${biasLabel}</span>
          <span class="regime-chip ${stressChipTone}">${r.stress_label}</span>
          <span class="regime-chip ${contextChipTone}">${r.context_label}</span>
          <span class="regime-chip ${tone}">${r.confidence}% confidence</span>
        </div>
      </div>
      <div class="regime-metrics">
        ${metrics.map(m => `
          <div class="regime-metric">
            <div class="label">${m.label}</div>
            <div class="value">${m.value}</div>
            <div class="sub">${m.sub}</div>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="signal-section-title">Direction signals</div>
    <div class="signal-grid">${directionSignalsHtml}</div>
    <div class="signal-section-title">Stress signals</div>
    <div class="signal-grid">${stressSignalsHtml}</div>
    <div class="signal-section-title">External context</div>
    <div class="signal-grid">${contextSignalsHtml}</div>
    <div class="chart-box chart-box-lg"><canvas id="regimeChart"></canvas></div>
  `;

  if (regimeChart) regimeChart.destroy();
  regimeChart = new Chart(document.getElementById('regimeChart').getContext('2d'), {
    type: 'line',
    data: {
      labels: history.map(h => h.date),
      datasets: [
        {
          label: 'Direction score',
          data: history.map(h => h.direction_score ?? h.regime_score),
          yAxisID: 'y',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.18,
          fill: 'origin',
          backgroundColor: 'rgba(0,212,255,0.08)',
          segment: {
            borderColor: ctx => ctx.p1.parsed.y >= 0 ? 'rgba(0,255,136,0.85)' : 'rgba(255,59,92,0.85)'
          },
          borderColor: 'rgba(0,212,255,0.85)',
        },
        {
          label: 'Stress score',
          data: history.map(h => h.stress_score),
          yAxisID: 'y',
          borderColor: 'rgba(245,158,11,0.9)',
          backgroundColor: 'rgba(245,158,11,0.10)',
          borderDash: [6, 6],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.15,
        },
        {
          label: 'Context score',
          data: history.map(h => h.context_score),
          yAxisID: 'y',
          borderColor: 'rgba(168,85,247,0.9)',
          backgroundColor: 'rgba(168,85,247,0.08)',
          borderDash: [2, 6],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.15,
        },
        {
          label: 'BTC',
          data: history.map(h => h.close),
          yAxisID: 'y1',
          borderColor: 'rgba(59,130,246,0.65)',
          pointRadius: 0,
          tension: 0.15,
          borderWidth: 1.5,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#9ca3af', font: { size: 12 }, usePointStyle: true, pointStyle: 'line' }
        },
        tooltip: {
          backgroundColor: 'rgba(17,24,39,0.95)',
          borderColor: 'rgba(0,212,255,0.2)', borderWidth: 1,
          titleColor: '#e8eaed', bodyColor: '#9ca3af',
          padding: 12, cornerRadius: 10,
          callbacks: {
            title: (items) => fmtDate(history[items[0].dataIndex].date),
            afterBody: (items) => {
              const h = history[items[0].dataIndex];
              return [
                `Режим: ${h.regime_label}`,
                `Direction: ${h.direction_score ?? h.regime_score}`,
                `Confidence: ${h.confidence}%`,
                `Stress: ${h.stress_score} (${h.stress_label})`,
                `Context: ${h.context_score} (${h.context_label})`
              ];
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: '#4b5563',
            maxTicksLimit: 14,
            callback: function(v) {
              const d = this.getLabelForValue(v);
              return d ? d.substring(0, 7) : '';
            }
          },
          grid: { display: false }
        },
        y: {
          position: 'left',
          min: -18,
          max: 18,
          ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 11 } },
          grid: { color: 'rgba(255,255,255,0.04)' }
        },
        y1: {
          position: 'right',
          type: 'logarithmic',
          ticks: {
            color: '#4b5563',
            font: { family: 'JetBrains Mono', size: 11 },
            callback: v => '$' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v)
          },
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}

function buildRisk(calendar, referenceDate) {
  const today = referenceDate || dashboardToday || localDateKey();
  let threshold = scoreThresholds.hot;
  let upcoming = calendar.filter(d => d.date >= today && d.score >= threshold).slice(0, 24);
  if (!upcoming.length) {
    threshold = scoreThresholds.warm;
    upcoming = calendar.filter(d => d.date >= today && d.score >= threshold).slice(0, 24);
  }
  const grid = document.getElementById('riskGrid');

  if (!upcoming.length) {
    grid.innerHTML = '<div class="loading" style="animation:none">Нет ближайших дней с повышенным reversal score</div>';
    return;
  }

  const todayDate = parseDateOnly(today);
  grid.innerHTML = upcoming.map(d => {
    const cls = riskClass(d.score);
    const daysAway = Math.round((parseDateOnly(d.date) - todayDate) / 86400000);
    const details = (d.details || '').split(' | ').filter(s => s.startsWith('+'));
    const dirHtml = d.direction > 0 ? '<span class="up">&#9650; Пик</span>'
                  : d.direction < 0 ? '<span class="down">&#9660; Дно</span>'
                  : 'Нейтрально';

    return `<div class="risk-item ${cls}">
      <div class="risk-badge ${cls}">${d.score.toFixed(1)}</div>
      <div class="risk-body">
        <div class="risk-date">${fmtDate(d.date)} <span class="days-away">${daysAway === 0 ? 'Сегодня' : 'через ' + daysAway + ' дн.'}</span></div>
        <div class="risk-dir">${dirHtml}</div>
        <div class="risk-meta">
          <span class="tag">☽ ${d.moon_sign}</span>
          <span class="tag">${d.moon_element}</span>
          <span class="tag">☉ ${d.sun_sign || ''}</span>
          <span class="tag">${d.quarter}</span>
          ${d.retro_planets ? '<span class="tag">Ретро: '+d.retro_planets+'</span>' : ''}
          ${d.station_planets ? '<span class="tag">Станция: '+d.station_planets+'</span>' : ''}
        </div>
        <div class="risk-details">${details.join('<br>')}</div>
      </div>
    </div>`;
  }).join('');
}

function buildStats(s) {
  const block = document.getElementById('statsBlock');
  const periodText = s.period_start && s.period_end
    ? `${fmtDate(s.period_start)} - ${fmtDate(s.period_end)}`
    : 'Период не указан';

  const thRows = s.thresholds.map(t => {
    const cls = t.lift >= 2 ? 'lift-good' : t.lift >= 1.2 ? 'lift-ok' : 'lift-meh';
    return `<tr>
      <td style="font-family:'JetBrains Mono'">&ge; ${Number(t.threshold).toFixed(1)}</td>
      <td>${t.days_count} <span style="color:var(--text2)">(${t.days_pct}%)</span></td>
      <td>${t.pivots_in_zone}</td>
      <td class="${cls}">${t.lift}x</td>
    </tr>`;
  }).join('');

  block.innerHTML = `
    <div style="font-size:12px;color:var(--text2);margin-bottom:14px;text-transform:uppercase;letter-spacing:0.8px">
      Holdout-валидация: ${periodText}
    </div>
    <div class="stats-row">
      <div class="stat-block">
        <div class="stat-val">${s.baseline_avg_score}</div>
        <div class="stat-label">Ср. балл (holdout дни)</div>
      </div>
      <div class="stat-block">
        <div class="stat-val accent-green">${s.pivot_avg_score}</div>
        <div class="stat-label">Ср. балл (holdout развороты)</div>
      </div>
      <div class="stat-block">
        <div class="stat-val accent-yellow">${s.total_pivots}</div>
        <div class="stat-label">Разворотов в holdout</div>
      </div>
      <div class="stat-block">
        <div class="stat-val">${s.direction_accuracy}%</div>
        <div class="stat-label">Точность направления</div>
      </div>
    </div>
    <div style="font-size:14px;font-weight:600;margin-bottom:8px;color:var(--text2)">Анализ порогов</div>
    <table>
      <thead><tr><th>Порог</th><th>Дней в holdout</th><th>Поймано разворотов</th><th>Lift</th></tr></thead>
      <tbody>${thRows}</tbody>
    </table>
  `;
}

init();
