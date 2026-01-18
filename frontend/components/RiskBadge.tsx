/**
 * 风险徽章组件
 */
import { RiskResponse } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AnimatedCardHover } from '@/components/ui/animated-card';
import { BorderBeam } from '@/components/ui/border-beam';

interface RiskBadgeProps {
  risk: RiskResponse;
}

const riskColors: Record<string, { bg: string; text: string; beamColor: string }> = {
  '🟢 低风险': { bg: 'bg-gradient-to-r from-emerald-100 to-green-100', text: 'text-emerald-800', beamColor: '#10b981' },
  '🟡 中等风险': { bg: 'bg-gradient-to-r from-amber-100 to-yellow-100', text: 'text-amber-800', beamColor: '#fbbf24' },
  '🔴 高风险': { bg: 'bg-gradient-to-r from-red-100 to-rose-100', text: 'text-red-800', beamColor: '#ef4444' },
};

export default function RiskBadge({ risk }: RiskBadgeProps) {
  const colors = riskColors[risk.Risk] || riskColors['🟡 中等风险'];

  return (
    <AnimatedCardHover>
      <Card className="relative overflow-hidden bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
        <BorderBeam 
          colorFrom={colors.beamColor} 
          colorTo={colors.beamColor}
          duration={10}
        />
        <CardHeader>
          <CardTitle className="text-lg">风险等级</CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`inline-block px-4 py-2 rounded-full ${colors.bg} ${colors.text} font-medium`}>
            {risk.Risk}
          </div>
          <div className="mt-4 text-sm text-muted-foreground">
            <p>风险评分: {risk.RiskScore}/6</p>
            <p>趋势: {risk.TrendUp ? '📈 上升' : '📉 下降'}</p>
          </div>
        </CardContent>
      </Card>
    </AnimatedCardHover>
  );
}
