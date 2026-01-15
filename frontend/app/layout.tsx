import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'Engineer Alpha 风险&买点工具',
  description: '输入股票代码，自动给出：建议动作（观察/试探/建仓/加仓）+ 风险等级 + 分批买点区间 + 加仓位置',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
