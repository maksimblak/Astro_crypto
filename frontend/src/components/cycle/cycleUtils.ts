export function zoneLabel(zone: string): string {
  const map: Record<string, string> = {
    top_zone: 'Top zone',
    top_watch: 'Top watch',
    bottom_zone: 'Bottom zone',
    bottom_watch: 'Bottom watch',
    mixed: 'Mixed',
  };
  return map[zone] || 'Neutral';
}
