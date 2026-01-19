/**
 * Buy Zones Component
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
        return { zone: zones.Conservative, name: 'Conservative' };
      case 'aggressive':
        return { zone: zones.Aggressive, name: 'Aggressive' };
      default:
        return { zone: zones.Neutral, name: 'Standard' };
    }
  };

  const recommended = getRecommendedZone();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Buy Zones (Batch, Not Bottom Guessing)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Conservative Zone */}
            <div className="rounded-lg p-4 border bg-muted">
              <h4 className="font-semibold text-foreground mb-2">🟦 Conservative</h4>
              <p className="text-sm text-muted-foreground mb-2">More Stable: Wait for pullback to a more comfortable position</p>
              <p className="text-lg font-medium text-foreground">
                {formatMoney(zones.Conservative[0])} ~ {formatMoney(zones.Conservative[1])}
              </p>
            </div>

            {/* Standard Zone */}
            <div className="rounded-lg p-4 border bg-muted">
              <h4 className="font-semibold text-foreground mb-2">🟩 Standard</h4>
              <p className="text-sm text-muted-foreground mb-2">Main Zone: Suitable for batch accumulation</p>
              <p className="text-lg font-medium text-foreground">
                {formatMoney(zones.Neutral[0])} ~ {formatMoney(zones.Neutral[1])}
              </p>
            </div>

            {/* Aggressive Zone */}
            <div className="rounded-lg p-4 border bg-muted">
              <h4 className="font-semibold text-foreground mb-2">🟥 Aggressive</h4>
              <p className="text-sm text-muted-foreground mb-2">Bottom Zone: High volatility, suitable for bold batch bottom fishing</p>
              <p className="text-lg font-medium text-foreground">
                {formatMoney(zones.Aggressive[0])} ~ {formatMoney(zones.Aggressive[1])}
              </p>
            </div>
          </div>

          <div className="border bg-muted rounded-lg p-4">
            <p className="text-foreground">
              You selected <strong>{mode === 'conservative' ? 'Conservative' : mode === 'aggressive' ? 'Aggressive' : 'Standard'}</strong> →
              Recommended to start batch accumulation from <strong>{recommended.name} Zone</strong>:
              {formatMoney(recommended.zone[0])} ~ {formatMoney(recommended.zone[1])}
            </p>
          </div>

          <p className="text-sm text-muted-foreground">
            Note: Zones are generated based on ATR (volatility) + mean deviation, they are &quot;batch zones&quot;, not bottom predictions.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
