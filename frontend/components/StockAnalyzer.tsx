/**
 * 股票分析器主组件
 */
'use client';

import { useState } from 'react';
import { AnalysisResponse, InvestmentMode } from '@/lib/types';
import { analyzeStock } from '@/lib/api';
import SignalCard from './SignalCard';
import RiskBadge from './RiskBadge';
import BuyZones from './BuyZones';

export default function StockAnalyzer() {
  const [ticker, setTicker] = useState('MSFT');
  const [years, setYears] = useState(10);
  const [mode, setMode] = useState<InvestmentMode>('standard');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  const handleAnalyze = async () => {
    if (!ticker.trim()) {
      setError('Ticker 不能为空');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await analyzeStock({
        ticker: ticker.trim().toUpperCase(),
        years,
        mode,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-2xl font-bold mb-6">Engineer Alpha 风险等级 & 买点区间</h2>
        
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                输入股票 Ticker（例如 MSFT / COIN / MSTR / RKLB）
              </label>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="MSFT"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">你的风格</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as InvestmentMode)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="conservative">保守</option>
                <option value="standard">标准（推荐）</option>
                <option value="aggressive">激进</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              历史回看长度（年）: {years}
            </label>
            <input
              type="range"
              min="2"
              max="15"
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '分析中...' : '生成分析'}
          </button>
        </div>

        {error && (
          <div className="mt-4 bg-red-100 border border-red-300 text-red-800 rounded-lg p-4">
            {error}
          </div>
        )}
      </div>

      {result && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-xl font-semibold mb-4">{ticker.toUpperCase()} — 结果</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <SignalCard signal={result.signal} />
              <RiskBadge risk={result.risk} />
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold mb-4">当前价格</h3>
                <p className="text-2xl font-bold text-blue-600">
                  ${result.signal.Last.toFixed(2)}
                </p>
              </div>
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <p className="text-blue-800">
                一句话：{' '}
                {result.signal.A_pos ? '位置偏低' : '位置不低'} ｜{' '}
                {result.signal.B_rsi ? 'RSI偏冷' : 'RSI不冷'} ｜{' '}
                {result.signal.C_turn ? '开始回暖' : '未回暖'}
                {' '}（用于分批决策，不预测涨跌）
              </p>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <BuyZones zones={result.zones} mode={mode} />
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-xl font-semibold mb-4">加仓位置（更像操作手册）</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">第一加仓（标准区下沿）</p>
                <p className="text-xl font-semibold">
                  ${result.add_levels.FirstAdd.toFixed(2)}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">回调加仓（抄底带中点）</p>
                <p className="text-xl font-semibold">
                  ${result.add_levels.PullbackAdd.toFixed(2)}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">价值洼地加仓</p>
                <p className="text-xl font-semibold">
                  {result.add_levels.ValuePocketAdd 
                    ? `$${result.add_levels.ValuePocketAdd.toFixed(2)}`
                    : '—'}
                </p>
              </div>
            </div>
            {result.add_levels.ValuePocketRule && (
              <p className="mt-4 text-sm text-gray-600">
                价值洼地规则：{result.add_levels.ValuePocketRule}（基本面字段缺失时可能不显示）
              </p>
            )}
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-xl font-semibold mb-4">为什么会给这个建议？（人话解释）</h3>
            <div className="space-y-3">
              <div>
                <p className="font-medium">
                  {result.signal.A_pos ? '✅' : '❌'} A 位置偏低
                </p>
                <p className="text-sm text-gray-600 ml-6">
                  近3年分位：{result.signal.Pct3Y !== null ? `${(result.signal.Pct3Y * 100).toFixed(0)}%` : '—'}；
                  近5年分位：{result.signal.Pct5Y !== null ? `${(result.signal.Pct5Y * 100).toFixed(0)}%` : '—'}
                  （分位越低=越接近历史低位）
                </p>
              </div>
              <div>
                <p className="font-medium">
                  {result.signal.B_rsi ? '✅' : '❌'} B 情绪偏冷（RSI偏低）
                </p>
                <p className="text-sm text-gray-600 ml-6">
                  RSI(14)：{result.signal.RSI.toFixed(1)}（&lt;35 通常代表偏冷/超卖区附近）
                </p>
              </div>
              <div>
                <p className="font-medium">
                  {result.signal.C_turn ? '✅' : '❌'} C 有回暖迹象（RSI拐头）
                </p>
                <p className="text-sm text-gray-600 ml-6">
                  最近 RSI 出现向上拐头，代表下跌动能减弱（不等于一定反转）
                </p>
              </div>
            </div>
          </div>

          <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-4">
            <p className="text-yellow-800 text-sm">
              <strong>免责声明：</strong>本工具仅用于研究与教育，不构成投资建议。市场有风险，投资需谨慎。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
