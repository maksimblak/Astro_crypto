const MO_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function fmtDate(d: string): string {
  const dt = parseDateOnly(d);
  return dt.getDate() + ' ' + MO_RU[dt.getMonth()] + ' ' + dt.getFullYear();
}

export function fmtShort(d: string): string {
  const dt = parseDateOnly(d);
  return dt.getDate() + ' ' + MO_RU[dt.getMonth()];
}

export function localDateKey(dt = new Date()): string {
  const year = dt.getFullYear();
  const month = String(dt.getMonth() + 1).padStart(2, '0');
  const day = String(dt.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function monthLabel(yearMonth: string): string {
  const dt = parseDateOnly(yearMonth + '-01');
  return MO_RU[dt.getMonth()] + ' ' + dt.getFullYear();
}
