/**
 * 买入区间组件
 */
import { ZonesResponse, InvestmentMode } from '@/lib/types';

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
    <div className="space-y-6">
      <h3 className="text-xl font-semibold">买入区间（分批，不猜底）</h3>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 保守区 */}
        <div className="bg-blue-50 rounded-lg p-4 border-2 border-blue-200">
          <h4 className="font-semibold text-blue-800 mb-2">🟦 保守</h4>
          <p className="text-sm text-gray-600 mb-2">更稳：等回调到更舒服的位置</p>
          <p className="text-lg font-medium">
            {formatMoney(zones.Conservative[0])} ~ {formatMoney(zones.Conservative[1])}
          </p>
        </div>

        {/* 标准区 */}
        <div className="bg-green-50 rounded-lg p-4 border-2 border-green-200">
          <h4 className="font-semibold text-green-800 mb-2">🟩 标准</h4>
          <p className="text-sm text-gray-600 mb-2">主力区：适合分批建仓</p>
          <p className="text-lg font-medium">
            {formatMoney(zones.Neutral[0])} ~ {formatMoney(zones.Neutral[1])}
          </p>
        </div>

        {/* 激进区 */}
        <div className="bg-red-50 rounded-lg p-4 border-2 border-red-200">
          <h4 className="font-semibold text-red-800 mb-2">🟥 激进</h4>
          <p className="text-sm text-gray-600 mb-2">抄底带：波动大，适合敢分批抄底</p>
          <p className="text-lg font-medium">
            {formatMoney(zones.Aggressive[0])} ~ {formatMoney(zones.Aggressive[1])}
          </p>
        </div>
      </div>

      <div className="bg-green-100 border border-green-300 rounded-lg p-4">
        <p className="text-green-800">
          你选择的是 <strong>{mode === 'conservative' ? '保守' : mode === 'aggressive' ? '激进' : '标准'}</strong> → 
          推荐从 <strong>{recommended.name}区间</strong> 开始分批：
          {formatMoney(recommended.zone[0])} ~ {formatMoney(recommended.zone[1])}
        </p>
      </div>

      <p className="text-sm text-gray-500">
        说明：区间基于 ATR（波动）+ 均值偏离生成，是"分批带"，不是预测底部。
      </p>
    </div>
  );
}
