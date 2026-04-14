/**
 * Safely formats a date to Beijing time (Asia/Shanghai).
 * Falls back to local date string if the timezone is not supported.
 */
export function getBeijingDate(date: Date): string {
  try {
    // Standardize to YYYY-MM-DD for reliable comparison across environments
    const formatter = new Intl.DateTimeFormat('en-CA', { // en-CA gives YYYY-MM-DD
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const [{ value: year }, , { value: month }, , { value: day }] = formatter.formatToParts(date);
    return `${year}-${month}-${day}`;
  } catch (e) {
    console.warn('Failed to get Beijing date, falling back to local ISO date:', e);
    return date.toISOString().split('T')[0];
  }
}

/**
 * Generates a unique key for history items to avoid React duplicate key warnings.
 */
export function generateHistoryItemKey(item: any, index: number): string {
  if (item.id) return item.id;
  const symbol = item.stockInfo?.symbol || 'unknown';
  const time = item.stockInfo?.lastUpdated || 'no-time';
  return `history-${symbol}-${time}-${index}`;
}
