/**
 * 买入区间组件
 */
import { ZonesResponse, InvestmentMode } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface BuyZonesProps {
  zones: ZonesResponse;
  mode: InvestmentMode;
}

function formatMoney(value: number | null): string {
  if (value === null) return '—';
  return `$${value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
}

export default function BuyZones({ zones, mode }: BuyZonesProps) {
  const getRecommendedZone = () => {
    switch (mode) {
      case 'conservative':
        return { zone: zones.Conservative, name: '保守' };
      case 'aggressive':
        return { zone: zones.Aggressive, name: '激进' };
      default:
        return { zone: zones.Neutral, name: '标准' };
    }
  };

  const recommended = getRecommendedZone();

  return (
    <Card className="bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
      <CardHeader>
        <CardTitle className="text-xl">买入区间（分批，不猜底）</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 保守区 */}
            <div className="bg-gradient-to-br from-blue-50/80 to-indigo-50/80 backdrop-blur-sm rounded-lg p-4 border border-blue-200/50 shadow-sm">
              <h4 className="font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent mb-2">🟦 保守</h4>
              <p className="text-sm text-gray-700 mb-2">更稳：等回调到更舒服的位置</p>
              <p className="text-lg font-medium bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                {formatMoney(zones.Conservative[0])} ~ {formatMoney(zones.Conservative[1])}
              </p>
            </div>

            {/* 标准区 */}
            <div className="bg-gradient-to-br from-emerald-50/80 to-green-50/80 backdrop-blur-sm rounded-lg p-4 border border-emerald-200/50 shadow-sm">
              <h4 className="font-semibold bg-gradient-to-r from-emerald-600 to-green-600 bg-clip-text text-transparent mb-2">🟩 标准</h4>
              <p className="text-sm text-gray-700 mb-2">主力区：适合分批建仓</p>
              <p className="text-lg font-medium bg-gradient-to-r from-emerald-600 to-green-600 bg-clip-text text-transparent">
                {formatMoney(zones.Neutral[0])} ~ {formatMoney(zones.Neutral[1])}
              </p>
            </div>

            {/* 激进区 */}
            <div className="bg-gradient-to-br from-red-50/80 to-rose-50/80 backdrop-blur-sm rounded-lg p-4 border border-red-200/50 shadow-sm">
              <h4 className="font-semibold bg-gradient-to-r from-red-600 to-rose-600 bg-clip-text text-transparent mb-2">🟥 激进</h4>
              <p className="text-sm text-gray-700 mb-2">抄底带：波动大，适合敢分批抄底</p>
              <p className="text-lg font-medium bg-gradient-to-r from-red-600 to-rose-600 bg-clip-text text-transparent">
                {formatMoney(zones.Aggressive[0])} ~ {formatMoney(zones.Aggressive[1])}
              </p>
            </div>
          </div>

          <div className="bg-gradient-to-r from-emerald-100/80 to-green-100/80 backdrop-blur-sm border border-emerald-300/50 rounded-lg p-4 shadow-sm">
            <p className="text-emerald-800">
              你选择的是 <strong>{mode === 'conservative' ? '保守' : mode === 'aggressive' ? '激进' : '标准'}</strong> →
              推荐从 <strong>{recommended.name}区间</strong> 开始分批：
              {formatMoney(recommended.zone[0])} ~ {formatMoney(recommended.zone[1])}
            </p>
          </div>

          <p className="text-sm text-muted-foreground">
            说明：区间基于 ATR（波动）+ 均值偏离生成，是"分批带"，不是预测底部。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
