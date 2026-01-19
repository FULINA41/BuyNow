/**
 * Risk Badge Component
 */
import { RiskResponse } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AnimatedCardHover } from '@/components/ui/animated-card';
import { BorderBeam } from '@/components/ui/border-beam';

interface RiskBadgeProps {
  risk: RiskResponse;
}

const riskColors: Record<string, { bg: string; text: string; beamColor: string }> = {
  '🟢 Low Risk': { bg: 'bg-muted', text: 'text-muted-foreground', beamColor: '#9ca3af' },
  '🟡 Medium Risk': { bg: 'bg-muted', text: 'text-muted-foreground', beamColor: '#9ca3af' },
  '🔴 High Risk': { bg: 'bg-muted', text: 'text-muted-foreground', beamColor: '#9ca3af' },
};

export default function RiskBadge({ risk }: RiskBadgeProps) {
  const colors = riskColors[risk.Risk] || riskColors['🟡 Medium Risk'];

  return (
    <AnimatedCardHover>
      <Card className="relative overflow-hidden">
        <CardHeader>
          <CardTitle className="text-lg">Risk Level</CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`inline-block px-4 py-2 rounded-full ${colors.bg} ${colors.text} font-medium`}>
            {risk.Risk}
          </div>
          <div className="mt-4 text-sm text-muted-foreground">
            <p>Risk Score: {risk.RiskScore}/6</p>
            <p>Trend: {risk.TrendUp ? '📈 Up' : '📉 Down'}</p>
          </div>
        </CardContent>
      </Card>
    </AnimatedCardHover>
  );
}
