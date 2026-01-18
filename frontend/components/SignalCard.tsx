/**
 * 信号卡片组件
 */
import { SignalResponse } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AnimatedCardHover } from '@/components/ui/animated-card';
import { BorderBeam } from '@/components/ui/border-beam';

interface SignalCardProps {
  signal: SignalResponse;
}

const signalBadges: Record<string, { emoji: string; color: string; beamColor: string }> = {
  观察: { emoji: '⚪', color: 'bg-gradient-to-r from-gray-100 to-slate-100 text-gray-700', beamColor: '#9ca3af' },
  试探: { emoji: '🟡', color: 'bg-gradient-to-r from-amber-100 to-yellow-100 text-amber-800', beamColor: '#fbbf24' },
  建仓: { emoji: '🟢', color: 'bg-gradient-to-r from-emerald-100 to-green-100 text-emerald-800', beamColor: '#10b981' },
  加仓: { emoji: '🔵', color: 'bg-gradient-to-r from-blue-100 to-cyan-100 text-blue-800', beamColor: '#3b82f6' },
};

export default function SignalCard({ signal }: SignalCardProps) {
  const badge = signalBadges[signal.Signal] || signalBadges['观察'];

  return (
    <AnimatedCardHover>
      <Card className="relative overflow-hidden bg-white/60 backdrop-blur-md border-white/30 shadow-lg">
        <BorderBeam 
          colorFrom={badge.beamColor} 
          colorTo={badge.beamColor}
          duration={10}
        />
        <CardHeader>
          <CardTitle className="text-lg">建议动作</CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`inline-block px-4 py-2 rounded-full ${badge.color} font-medium`}>
            {badge.emoji} {signal.Signal}
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex items-center gap-2">
              {signal.A_pos ? '✅' : '❌'} <span>位置偏低</span>
            </div>
            <div className="flex items-center gap-2">
              {signal.B_rsi ? '✅' : '❌'} <span>RSI偏冷</span>
            </div>
            <div className="flex items-center gap-2">
              {signal.C_turn ? '✅' : '❌'} <span>开始回暖</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </AnimatedCardHover>
  );
}
