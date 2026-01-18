import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'Engineer Alpha | AI Risk & Entry Point Tool',
  description: 'Enter a stock ticker, AI automatically generates: recommended actions, risk levels, batch entry zones, and add-on positions.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-white/20 selection:text-white bg-black text-white">
        <Providers>
          {/* Background container: fixed, full screen - black to gray gradient */}
          <div className="fixed inset-0 -z-10 h-full w-full bg-gradient-to-b from-black via-gray-950 to-gray-900">

            {/* Base grid: white grid lines */}
            <div className="absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />
          </div>

          {/* Content container */}
          <main className="relative z-10 mx-auto min-h-screen max-w-7xl px-4 sm:px-6 lg:px-8 py-12 md:py-24 ">
            <div className="flex flex-col items-center">
              {children}
            </div>
          </main>

          {/* Bottom decoration: black gradient */}
          <div className="fixed bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-black to-transparent pointer-events-none z-0" />
        </Providers>
      </body>
    </html>
  )
}