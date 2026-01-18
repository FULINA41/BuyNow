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
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { AnimatedCard } from '@/components/ui/animated-card';
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import { SearchIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

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
    <div className="max-w-6xl mx-auto p-6 space-y-6 relative z-20">
      <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
        <CardHeader>
          <CardTitle>Engineer Alpha 风险等级 & 买点区间</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>
                      <SearchIcon className="w-4 h-4" />
                    </InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput type="text" value={undefined} onChange={(e) => setTicker(e.target.value)} placeholder="Please enter the ticker" />
                </InputGroup>
              </div>

              <div className="relative z-30">
                <Select
                  value={mode}
                  onValueChange={(value: string) => setMode(value as InvestmentMode)}
                >
                  <SelectTrigger className="w-full relative z-30">
                    <SelectValue placeholder="选择风格" />
                  </SelectTrigger>
                  <SelectContent className="z-[200]">
                    <SelectItem value="conservative">保守</SelectItem>
                    <SelectItem value="standard">标准（推荐）</SelectItem>
                    <SelectItem value="aggressive">激进</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="mb-2 block">
                历史回看长度（年）: {years}
              </Label>
              <Slider
                min={2}
                max={15}
                value={[years]}
                onValueChange={(val) => setYears(val[0])}
                className={cn(
                  "w-[60%]",
                  // 修改已选中的轨道颜色为蓝色
                  "[&>.relative>.absolute]:bg-black/60",
                  // 修改滑块的边框颜色
                  "[&_[role=slider]]:bg-gray-300 [&_[role=slider]]:border-black",
                  // 修改未选中轨道的背景
                  "[&>.relative]:bg-black-100"
                )}
              />
            </div>

            <Button
              onClick={handleAnalyze}
              disabled={loading}
              className="w-full relative z-30"
            >
              {loading ? '分析中...' : '生成分析'}
            </Button>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-200/50 bg-gradient-to-r from-red-50/80 to-orange-50/80 backdrop-blur-sm p-4 text-red-700 bg-black/10">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6">
          <AnimatedCard delay={0.1}>
            <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
              <CardHeader>
                <CardTitle className="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">{ticker.toUpperCase()} — 结果</CardTitle>
              </CardHeader>
              <CardContent>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  <SignalCard signal={result.signal} />
                  <RiskBadge risk={result.risk} />
                  <Card className="bg-gradient-to-br from-blue-50/60 to-cyan-50/60 border-blue-200/30">
                    <CardHeader>
                      <CardTitle className="text-lg">当前价格</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
                        ${result.signal.Last.toFixed(2)}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                <div className="rounded-lg border border-purple-200/50 bg-gradient-to-r from-purple-50/60 to-pink-50/60 backdrop-blur-sm p-4 mb-6">
                  <p className="text-gray-700">
                    一句话：{' '}
                    {result.signal.A_pos ? '位置偏低' : '位置不低'} ｜{' '}
                    {result.signal.B_rsi ? 'RSI偏冷' : 'RSI不冷'} ｜{' '}
                    {result.signal.C_turn ? '开始回暖' : '未回暖'}
                    {' '}（用于分批决策，不预测涨跌）
                  </p>
                </div>
              </CardContent>
            </Card>
          </AnimatedCard>

          <AnimatedCard delay={0.2}>
            <BuyZones zones={result.zones} mode={mode} />
          </AnimatedCard>

          <AnimatedCard delay={0.3}>
            <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
              <CardHeader>
                <CardTitle>加仓位置（更像操作手册）</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="rounded-lg border border-indigo-200/50 bg-gradient-to-br from-indigo-50/60 to-purple-50/60 backdrop-blur-sm p-4">
                    <p className="text-sm text-gray-700 mb-1">第一加仓（标准区下沿）</p>
                    <p className="text-xl font-semibold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                      ${result.add_levels.FirstAdd.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-blue-200/50 bg-gradient-to-br from-blue-50/60 to-cyan-50/60 backdrop-blur-sm p-4">
                    <p className="text-sm text-gray-700 mb-1">回调加仓（抄底带中点）</p>
                    <p className="text-xl font-semibold bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
                      ${result.add_levels.PullbackAdd.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-emerald-200/50 bg-gradient-to-br from-emerald-50/60 to-teal-50/60 backdrop-blur-sm p-4">
                    <p className="text-sm text-gray-700 mb-1">价值洼地加仓</p>
                    <p className="text-xl font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">
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
              </CardContent>
            </Card>
          </AnimatedCard>

          <AnimatedCard delay={0.4}>
            <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
              <CardHeader>
                <CardTitle>为什么会给这个建议？（人话解释）</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <p className="font-medium">
                      {result.signal.A_pos ? '✅' : '❌'} A 位置偏低
                    </p>
                    <p className="text-sm text-gray-700 ml-6">
                      近3年分位：{result.signal.Pct3Y !== null ? `${(result.signal.Pct3Y * 100).toFixed(0)}%` : '—'}；
                      近5年分位：{result.signal.Pct5Y !== null ? `${(result.signal.Pct5Y * 100).toFixed(0)}%` : '—'}
                      （分位越低=越接近历史低位）
                    </p>
                  </div>
                  <div>
                    <p className="font-medium">
                      {result.signal.B_rsi ? '✅' : '❌'} B 情绪偏冷（RSI偏低）
                    </p>
                    <p className="text-sm text-gray-700 ml-6">
                      RSI(14)：{result.signal.RSI.toFixed(1)}（&lt;35 通常代表偏冷/超卖区附近）
                    </p>
                  </div>
                  <div>
                    <p className="font-medium">
                      {result.signal.C_turn ? '✅' : '❌'} C 有回暖迹象（RSI拐头）
                    </p>
                    <p className="text-sm text-gray-700 ml-6">
                      最近 RSI 出现向上拐头，代表下跌动能减弱（不等于一定反转）
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </AnimatedCard>

          <AnimatedCard delay={0.5}>
            <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
              <CardContent>
                <div className="rounded-lg border border-amber-200/50 bg-gradient-to-r from-amber-50/80 to-orange-50/80 backdrop-blur-sm p-4">
                  <p className="text-amber-800 text-sm">
                    <strong>免责声明：</strong>本工具仅用于研究与教育，不构成投资建议。市场有风险，投资需谨慎。
                  </p>
                </div>
              </CardContent>
            </Card>
          </AnimatedCard>
        </div>
      )}
    </div>
  );
}
