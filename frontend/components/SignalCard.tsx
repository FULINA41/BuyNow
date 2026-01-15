/**
 * 信号卡片组件
 */
import { SignalResponse } from '@/lib/types';

interface SignalCardProps {
  signal: SignalResponse;
}

const signalBadges: Record<string, { emoji: string; color: string }> = {
  观察: { emoji: '⚪', color: 'bg-gray-100 text-gray-800' },
  试探: { emoji: '🟡', color: 'bg-yellow-100 text-yellow-800' },
  建仓: { emoji: '🟢', color: 'bg-green-100 text-green-800' },
  加仓: { emoji: '🔵', color: 'bg-blue-100 text-blue-800' },
};

export default function SignalCard({ signal }: SignalCardProps) {
  const badge = signalBadges[signal.Signal] || signalBadges['观察'];

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-lg font-semibold mb-4">建议动作</h3>
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
    </div>
  );
}
