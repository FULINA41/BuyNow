/**
 * 风险徽章组件
 */
import { RiskResponse } from '@/lib/types';

interface RiskBadgeProps {
  risk: RiskResponse;
}

const riskColors: Record<string, { bg: string; text: string }> = {
  '🟢 低风险': { bg: 'bg-green-100', text: 'text-green-800' },
  '🟡 中等风险': { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  '🔴 高风险': { bg: 'bg-red-100', text: 'text-red-800' },
};

export default function RiskBadge({ risk }: RiskBadgeProps) {
  const colors = riskColors[risk.Risk] || riskColors['🟡 中等风险'];

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-lg font-semibold mb-4">风险等级</h3>
      <div className={`inline-block px-4 py-2 rounded-full ${colors.bg} ${colors.text} font-medium`}>
        {risk.Risk}
      </div>
      <div className="mt-4 text-sm text-gray-600">
        <p>风险评分: {risk.RiskScore}/6</p>
        <p>趋势: {risk.TrendUp ? '📈 上升' : '📉 下降'}</p>
      </div>
    </div>
  );
}
