/**
 * Signal Card Component
 */
import { SignalResponse } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AnimatedCardHover } from '@/components/ui/animated-card';
import { BorderBeam } from '@/components/ui/border-beam';

interface SignalCardProps {
  signal: SignalResponse;
}

const signalBadges: Record<string, { emoji: string; color: string; beamColor: string }> = {
  观察: { emoji: '⚪', color: 'bg-muted text-muted-foreground', beamColor: '#9ca3af' },
  试探: { emoji: '🟡', color: 'bg-muted text-muted-foreground', beamColor: '#9ca3af' },
  建仓: { emoji: '🟢', color: 'bg-muted text-muted-foreground', beamColor: '#9ca3af' },
  加仓: { emoji: '🔵', color: 'bg-muted text-muted-foreground', beamColor: '#9ca3af' },
};

export default function SignalCard({ signal }: SignalCardProps) {
  const badge = signalBadges[signal.Signal] || signalBadges['观察'];

  return (
    <AnimatedCardHover>
      <Card className="relative overflow-hidden">
        <CardHeader>
          <CardTitle className="text-lg">Recommended Action</CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`inline-block px-4 py-2 rounded-full ${badge.color} font-medium`}>
            {badge.emoji} {signal.Signal}
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex items-center gap-2">
              {signal.A_pos ? '✅' : '❌'} <span>Position Low</span>
            </div>
            <div className="flex items-center gap-2">
              {signal.B_rsi ? '✅' : '❌'} <span>RSI Cold</span>
            </div>
            <div className="flex items-center gap-2">
              {signal.C_turn ? '✅' : '❌'} <span>Starting Recovery</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </AnimatedCardHover>
  );
}
