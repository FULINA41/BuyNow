import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'Engineer Alpha | AI 风险&买点工具',
  description: '输入股票代码，AI 自动生成：建议动作、风险等级、分批买点区间及加仓位置。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="light"> {/* 改为 light 模式 */}
      <body className="antialiased selection:bg-blue-100 selection:text-blue-700 bg-slate-50 text-slate-900">
        <Providers>
          {/* 背景容器：固定、全屏 */}
          <div className="fixed inset-0 -z-10 h-full w-full bg-[#fdfeff]">
            
            {/* 1. 基础网格：浅色模式下网格要更淡 (使用 #00000005 这种极淡的黑色) */}
            <div className="absolute inset-0 z-0 bg-[linear-gradient(to_right,#0000005_1px,transparent_1px),linear-gradient(to_bottom,#00000005_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />

            {/* 2. 浅色柔光：不再是强烈的发光，而是像淡淡的墨水晕开 */}
            {/* 左上角淡蓝色光晕 */}
            <div className="absolute left-[10%] top-[-10%] h-[600px] w-[600px] rounded-full bg-blue-200/80 blur-[100px]" />
            {/* 中间偏右的淡紫色光晕 */}
            <div className="absolute right-[5%] top-[10%] h-[500px] w-[500px] rounded-full bg-purple-200/80 blur-[100px]" />
          </div>

          {/* 内容容器 */}
          <main className="relative z-10 mx-auto min-h-screen max-w-7xl px-4 sm:px-6 lg:px-8 py-12 md:py-24 ">
            <div className="flex flex-col items-center">
              {children}
            </div>
          </main>

          {/* 底部装饰：浅色模式下通常不需要底部遮罩，或者使用非常淡的白渐变 */}
          <div className="fixed bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#fdfeff] to-transparent pointer-events-none z-0" />
        </Providers>
      </body>
    </html>
  )
}