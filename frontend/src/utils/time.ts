/**
 * Centralized Timezone and Timestamp Utility for AI Market Analyzer.
 *
 * Guarantees that ALL instruments (including Indian exchange NSE/BSE and cryptocurrency BTC/USD)
 * are formatted strictly in Asia/Kolkata (IST, UTC+05:30) for all user-facing displays.
 */

export const MARKET_TIMEZONE = 'Asia/Kolkata';
export const UTC_TIMEZONE = 'Asia/Kolkata';

export function isCryptoInstrument(symbolOrTicker?: string): boolean {
  if (!symbolOrTicker) return false;
  const s = symbolOrTicker.toUpperCase();
  return s.includes('BTC') || s.includes('ETH') || s.includes('USD') || s.includes('CRYPTO');
}

export function getInstrumentTimezone(_symbolOrTicker?: string): string {
  // All user-facing instruments must display in Indian Standard Time (Asia/Kolkata)
  return MARKET_TIMEZONE;
}

/**
 * Safely converts any timestamp (ISO string, epoch ms/sec, Date) into a JavaScript Date object.
 * Naive ISO datetime strings without explicit offset (e.g. '2026-08-31 07:00:00' or '2026-08-31T07:00:00')
 * are normalized to UTC by appending 'Z' to avoid client-local timezone interpretation.
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

  let s = String(ts).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(s) && !/([+-]\d{2}:?\d{2}|Z)$/i.test(s)) {
    s = s.replace(' ', 'T') + 'Z';
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Formats time as 'hh:mm A IST' (or 'hh:mm A').
 * Example: '09:15 AM IST' or '12:30 PM IST'
 */
export function formatMarketTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string,
  includeSuffix: boolean = true
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = ' IST';

  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const formatted = formatter.format(d);
    return includeSuffix ? `${formatted}${suffix}` : formatted;
  } catch (e) {
    return d.toLocaleTimeString();
  }
}

/**
 * Formats intraday candle time as 'hh:mm A' in Asia/Kolkata (IST).
 * Example: '12:30 PM'
 */
export function formatCandleTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  return formatMarketTime(ts, symbolOrTicker, false);
}

/**
 * Formats candle date as 'DD MMM YYYY' in Asia/Kolkata (IST).
 * Example: '31 Aug 2026'
 */
export function formatCandleDate(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  try {
    const formatter = new Intl.DateTimeFormat('en-GB', {
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
 * Formats full datetime as 'DD MMM YYYY, hh:mm A IST' in Asia/Kolkata.
 * Example: '31 Aug 2026, 12:30 PM IST'
 */
export function formatMarketDateTime(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string,
  includeSuffix: boolean = true
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = ' IST';

  try {
    const dateFormatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
    const timeFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const datePart = dateFormatter.format(d);
    const timePart = timeFormatter.format(d);
    return `${datePart}, ${timePart}${includeSuffix ? suffix : ''}`;
  } catch (e) {
    return d.toLocaleString();
  }
}

/**
 * Formats clock/last updated time as 'hh:mm:ss A IST' in Asia/Kolkata.
 * Example: '12:30:45 PM IST'
 */
export function formatMarketTimeWithSeconds(
  ts: string | number | Date | null | undefined,
  symbolOrTicker?: string
): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';

  const tz = getInstrumentTimezone(symbolOrTicker);
  const suffix = ' IST';

  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
    return `${formatter.format(d)}${suffix}`;
  } catch (e) {
    return d.toLocaleTimeString();
  }
}

