import StockAnalyzer from '@/components/StockAnalyzer';

export default function Home() {
  return (
    <div className="bg-gradient-to-br from-purple-50/80 via-pink-50/80 to-blue-50/80 backdrop-blur-xl border border-white/20 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-3xl">
      <StockAnalyzer />
    </div>
  );
}
