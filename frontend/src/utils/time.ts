/**
 * Centralized Timezone and Timestamp Utility for AI Market Analyzer.
 *
 * Guarantees that all Indian exchange instruments (NSE, BSE) are formatted
 * strictly in Asia/Kolkata (IST, UTC+05:30) regardless of the client machine's local timezone.
 *
 * Cryptocurrency / 24/7 global instruments use UTC.
 */

export const MARKET_TIMEZONE = 'Asia/Kolkata';
export const UTC_TIMEZONE = 'UTC';

export function isCryptoInstrument(symbolOrTicker?: string): boolean {
  if (!symbolOrTicker) return false;
  const s = symbolOrTicker.toUpperCase();
  return s.includes('BTC') || s.includes('ETH') || s.includes('USD') || s.includes('CRYPTO');
}

export function getInstrumentTimezone(symbolOrTicker?: string): string {
  return isCryptoInstrument(symbolOrTicker) ? UTC_TIMEZONE : MARKET_TIMEZONE;
}

/**
 * Safely converts any timestamp (ISO string, epoch ms/sec, Date) into a JavaScript Date object.
 */
export function parseTimestamp(ts: string | number | Date | null | undefined): Date | null {
  if (!ts) return null;
  if (ts instanceof Date) return isNaN(ts.getTime()) ? null : ts;

  if (typeof ts === 'number') {
    // Handle seconds vs milliseconds epoch
    const ms = ts < 1e11 ? ts * 1000 : ts;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? null : d;
  }

  const s = String(ts).trim();
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Formats time as 'HH:mm IST' (or 'HH:mm UTC' / 'HH:mm').
 * Example: '09:15 IST'
 */
export function formatMarketTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string,
  includeSuffix: boolean = true
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = tz === MARKET_TIMEZONE ? ' IST' : (tz === UTC_TIMEZONE ? ' UTC' : '');

  try {
    const formatter = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
    const formatted = formatter.format(d);
    return includeSuffix ? `${formatted}${suffix}` : formatted;
  } catch (e) {
    return d.toLocaleTimeString();
  }
}

/**
 * Formats intraday candle time as 'HH:mm' in the market timezone.
 * Example: '09:15'
 */
export function formatCandleTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  return formatMarketTime(ts, symbolOrTicker, false);
}

/**
 * Formats candle date as 'DD MMM YYYY' in the market timezone.
 * Example: '25 Aug 2026'
 */
export function formatCandleDate(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  try {
    const formatter = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
    return formatter.format(d);
  } catch (e) {
    return d.toLocaleDateString();
  }
}

/**
 * Formats full datetime as 'DD MMM YYYY, HH:mm IST'
 * Example: '25 Aug 2026, 09:15 IST'
 */
export function formatMarketDateTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string,
  includeSuffix: boolean = true
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = tz === MARKET_TIMEZONE ? ' IST' : (tz === UTC_TIMEZONE ? ' UTC' : '');

  try {
    const dateFormatter = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
    const timeFormatter = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
    const datePart = dateFormatter.format(d);
    const timePart = timeFormatter.format(d);
    return `${datePart}, ${timePart}${includeSuffix ? suffix : ''}`;
  } catch (e) {
    return d.toLocaleString();
  }
}

/**
 * Formats clock/last updated time as 'HH:mm:ss IST'
 * Example: '10:43:27 IST'
 */
export function formatMarketTimeWithSeconds(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = tz === MARKET_TIMEZONE ? ' IST' : (tz === UTC_TIMEZONE ? ' UTC' : '');

  try {
    const formatter = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
    return `${formatter.format(d)}${suffix}`;
  } catch (e) {
    return d.toLocaleTimeString();
  }
}
