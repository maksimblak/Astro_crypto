const sections = [
  { id: 'sectionCalendar', label: 'Календарь' },
  { id: 'sectionChart', label: 'График' },
  { id: 'sectionCycle', label: 'Пики / Дно' },
  { id: 'sectionRegime', label: 'Режим' },
  { id: 'sectionRisk', label: 'Зоны риска' },
  { id: 'sectionStats', label: 'Статистика' },
];

export default function TopBar() {
  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="topbar">
      <div className="topbar-inner">
        <div className="logo">
          <div className="logo-icon">&#9790;</div>
          <div>Astro<span>BTC</span></div>
        </div>
        <div className="nav-pills">
          {sections.map(s => (
            <button key={s.id} className="nav-pill" onClick={() => scrollTo(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
