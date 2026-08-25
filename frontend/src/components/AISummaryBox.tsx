import React, { useState } from 'react';
import { AIAnalysisSummary } from '../types';
import { Sparkles, Copy, Check, RefreshCw, AlertCircle, Bot } from 'lucide-react';

interface AISummaryBoxProps {
  symbol: string;
  summary: AIAnalysisSummary | null;
  onGenerateSummary: () => void;
  isLoading: boolean;
}

export const AISummaryBox: React.FC<AISummaryBoxProps> = ({
  symbol,
  summary,
  onGenerateSummary,
  isLoading
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!summary?.summary_markdown) return;
    navigator.clipboard.writeText(summary.summary_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="glass-panel rounded-2xl p-5 shadow-xs flex flex-col gap-4 bg-white border border-slate-200 relative overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-blue-50 text-blue-600 border border-blue-200">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-slate-900 flex items-center gap-2">
              <span>AI Share Market Prediction Narrative</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                {summary?.model_used || 'Gemini AI Assistant'}
              </span>
            </h3>
            <p className="text-xs text-slate-500">
              Anti-hallucinatory narrative derived strictly from quantitative structure data
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {summary && (
            <button
              onClick={handleCopy}
              className="px-2.5 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium flex items-center gap-1.5 transition-all shadow-2xs"
              title="Copy Summary Markdown"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          )}

          <button
            onClick={onGenerateSummary}
            disabled={isLoading}
            className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-all disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Analyzing...' : summary ? 'Refresh AI Analysis' : 'Generate AI Summary'}</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      {summary ? (
        <div className="bg-slate-50/70 rounded-xl p-4 border border-slate-200 text-slate-800 text-xs leading-relaxed max-h-[460px] overflow-y-auto space-y-3 font-sans">
          {summary.summary_markdown.split('## ').map((section, idx) => {
            if (!section.trim()) return null;
            const lines = section.trim().split('\n');
            const heading = lines[0];
            const content = lines.slice(1).join('\n');

            return (
              <div key={idx} className="border-b border-slate-200 pb-3 last:border-0 last:pb-0">
                <h4 className="text-sm font-bold text-blue-700 mb-1.5 flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
                  {heading}
                </h4>
                <div className="whitespace-pre-line text-slate-700 font-normal pl-3">
                  {content}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="py-12 flex flex-col items-center justify-center text-center bg-slate-50 rounded-xl border border-dashed border-slate-300 p-6">
          <Bot className="h-10 w-10 text-blue-500 mb-2" />
          <h4 className="font-semibold text-slate-800 text-sm">No AI Summary Generated Yet</h4>
          <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
            Click the button above to generate a comprehensive multi-timeframe analytical summary powered by Gemini.
          </p>
          <button
            onClick={onGenerateSummary}
            disabled={isLoading}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition-all shadow-xs flex items-center gap-2"
          >
            <Sparkles className="h-4 w-4" />
            <span>Generate Analysis for {symbol}</span>
          </button>
        </div>
      )}

      {/* Compliance Disclaimer */}
      <div className="flex items-center gap-2 text-[10px] text-slate-500 bg-slate-50 px-3 py-2 rounded-lg border border-slate-200">
        <AlertCircle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
        <span>
          Educational decision-support only. The AI reasons strictly from quantitative data and does NOT guarantee market movements.
        </span>
      </div>
    </div>
  );
};
