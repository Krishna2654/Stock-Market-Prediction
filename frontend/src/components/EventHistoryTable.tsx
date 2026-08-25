import React, { useState } from 'react';
import { StructureBreakEvent, AlertNotification } from '../types';
import { formatMarketDateTime } from '../utils/time';
import { History, Download, Filter, Search, ShieldCheck } from 'lucide-react';

interface EventHistoryTableProps {
  notifications: AlertNotification[];
  onClear: () => void;
}

export const EventHistoryTable: React.FC<EventHistoryTableProps> = ({
  notifications,
  onClear
}) => {
  const [filterTimeframe, setFilterTimeframe] = useState<string>('ALL');
  const [filterEventType, setFilterEventType] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  const filtered = notifications.filter((n) => {
    if (filterTimeframe !== 'ALL' && n.timeframe !== filterTimeframe) return false;
    if (filterEventType !== 'ALL' && !n.event_type.includes(filterEventType)) return false;
    if (searchTerm && !n.symbol.toLowerCase().includes(searchTerm.toLowerCase()) && !n.message.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  const exportCSV = () => {
    if (filtered.length === 0) return;
    const headers = ['Time', 'Symbol', 'Timeframe', 'Event', 'Price', 'Level', 'Volume Confirmed', 'HTF Alignment', 'Evidence Score', 'Message'];
    const rows = filtered.map((n) => [
      n.timestamp,
      n.symbol,
      n.timeframe,
      n.event_type,
      n.price,
      n.level,
      n.volume_confirmed ? 'YES' : 'NO',
      n.htf_alignment,
      n.evidence_score,
      `"${n.message.replace(/"/g, '""')}"`
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `market_structure_events_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportJSON = () => {
    if (filtered.length === 0) return;
    const jsonString = `data:text/json;charset=utf-8,${encodeURIComponent(JSON.stringify(filtered, null, 2))}`;
    const link = document.createElement('a');
    link.setAttribute('href', jsonString);
    link.setAttribute('download', `market_structure_events_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="w-full glass-panel rounded-2xl p-5 shadow-xl flex flex-col gap-4">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2.5">
          <History className="h-5 w-5 text-cyan-400" />
          <div>
            <h2 className="font-bold text-base text-slate-100">
              Historical Market Structure Event Log
            </h2>
            <p className="text-xs text-slate-400">
              Audit trail of detected BOS, CHoCH, and Breakout confirmations
            </p>
          </div>
        </div>

        {/* Filter & Export Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Search symbol/event..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 w-44"
            />
          </div>

          {/* Timeframe Filter */}
          <select
            value={filterTimeframe}
            onChange={(e) => setFilterTimeframe(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Timeframes</option>
            <option value="4H">4H</option>
            <option value="1H">1H</option>
            <option value="15M">15M</option>
            <option value="5M">5M</option>
          </select>

          {/* Event Type Filter */}
          <select
            value={filterEventType}
            onChange={(e) => setFilterEventType(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Events</option>
            <option value="BOS">BOS</option>
            <option value="CHOCH">CHoCH</option>
            <option value="BREAKOUT">Breakout</option>
            <option value="ALIGNMENT">HTF Alignment</option>
          </select>

          {/* Export CSV */}
          <button
            onClick={exportCSV}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 transition-all"
            title="Export CSV"
          >
            <Download className="h-3.5 w-3.5 text-cyan-400" />
            <span>CSV</span>
          </button>

          {/* Export JSON */}
          <button
            onClick={exportJSON}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 transition-all"
            title="Export JSON"
          >
            <Download className="h-3.5 w-3.5 text-indigo-400" />
            <span>JSON</span>
          </button>

          {/* Clear */}
          <button
            onClick={onClear}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-rose-400 hover:text-rose-300 text-xs font-medium transition-all"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Events Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-slate-900/90 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
              <th className="py-2.5 px-3">Time</th>
              <th className="py-2.5 px-3">Instrument</th>
              <th className="py-2.5 px-2 text-center">TF</th>
              <th className="py-2.5 px-3">Event</th>
              <th className="py-2.5 px-3 font-mono">Price</th>
              <th className="py-2.5 px-3 font-mono">Broken Level</th>
              <th className="py-2.5 px-2 text-center">Volume Conf.</th>
              <th className="py-2.5 px-2 text-center">HTF Align</th>
              <th className="py-2.5 px-2 text-center">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-sans">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-400">
                  No historical structure events recorded matching your filters.
                </td>
              </tr>
            ) : (
              filtered.map((evt) => {
                const isBull = evt.event_type.includes('BULLISH') || evt.htf_alignment === 'BULLISH';
                return (
                  <tr key={evt.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="py-2.5 px-3 whitespace-nowrap text-slate-400 font-mono text-[11px]">
                      {formatMarketDateTime(evt.timestamp, evt.symbol)}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-100 whitespace-nowrap">
                      {evt.symbol}
                    </td>
                    <td className="py-2.5 px-2 text-center whitespace-nowrap">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 font-mono font-bold text-[10px] text-cyan-400">
                        {evt.timeframe}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap font-semibold">
                      <span className={`px-2 py-0.5 rounded text-[11px] ${
                        isBull
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                          : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                      }`}>
                        {evt.event_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono font-bold text-slate-200 whitespace-nowrap">
                      ₹{evt.price.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-slate-400 whitespace-nowrap">
                      ₹{evt.level.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-2 text-center whitespace-nowrap">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        evt.volume_confirmed
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-slate-800 text-slate-400'
                      }`}>
                        {evt.volume_confirmed ? 'YES' : 'NO'}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-center whitespace-nowrap">
                      <span className="font-semibold text-[11px] text-slate-300">
                        {evt.htf_alignment}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-center whitespace-nowrap">
                      <span className="font-mono font-bold text-cyan-300">
                        {evt.evidence_score}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
