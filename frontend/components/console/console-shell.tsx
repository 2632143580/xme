'use client'

import { useState } from 'react'
import { AmbientGlow } from './ambient-glow'
import { ConsoleProvider } from './console-provider'
import { ChatPanel } from './chat/chat-panel'
import { ControlPanel, type ControlTab } from './control/control-panel'
import { SideNav, type NavKey } from './side-nav'
import { Toasts } from './toasts'
import { TopBar } from './top-bar'
import { cn } from '@/lib/utils'

export function ConsoleShell() {
  const [controlTab, setControlTab] = useState<ControlTab>('status')
  const [mobileView, setMobileView] = useState<'chat' | 'control'>('chat')

  const activeNav: NavKey = mobileView === 'chat' ? 'chat' : controlTab

  const handleSelect = (key: NavKey) => {
    if (key === 'chat') {
      setMobileView('chat')
    } else {
      setControlTab(key)
      setMobileView('control')
    }
  }

  return (
    <ConsoleProvider>
      <AmbientGlow />
      <div className="flex min-h-dvh flex-col">
        <TopBar />

        <div className="flex min-h-0 flex-1 lg:overflow-hidden">
          <SideNav active={activeNav} onSelect={handleSelect} />

          {/* 主区：桌面双栏并列；移动端按导航切换单栏 */}
          <main className="flex min-h-0 flex-1 gap-4 p-3 pb-24 md:p-4 lg:gap-5 lg:overflow-hidden lg:p-5 lg:pb-5">
            <div
              className={cn(
                'min-h-0 w-full flex-col lg:flex lg:w-[clamp(340px,38%,460px)]',
                mobileView === 'chat' ? 'flex' : 'hidden',
              )}
            >
              <ChatPanel />
            </div>

            <div
              className={cn(
                'min-h-0 w-full flex-1 flex-col lg:flex',
                mobileView === 'control' ? 'flex' : 'hidden',
              )}
            >
              <ControlPanel tab={controlTab} />
            </div>
          </main>
        </div>

        <Toasts />
      </div>
    </ConsoleProvider>
  )
}
