'use client'

import { ConfigTab } from './config-tab'
import { LogsTab } from './logs-tab'
import { StatusTab } from './status-tab'
import { WechatTab } from './wechat-tab'

export type ControlTab = 'status' | 'config' | 'logs' | 'wechat'

const META: Record<ControlTab, { title: string; sub: string }> = {
  status: { title: '状态', sub: '系统的脉搏与记忆的轮廓' },
  config: { title: '配置', sub: '调节它如何思考与存留' },
  logs: { title: '日志', sub: '它在沉默中留下的痕迹' },
  wechat: { title: '微信', sub: '通往日常对话的通道' },
}

export function ControlPanel({ tab }: { tab: ControlTab }) {
  const meta = META[tab]
  return (
    <section
      aria-label={meta.title}
      className="glass flex min-h-0 flex-1 flex-col rounded-2xl border border-border/50"
    >
      <header className="border-b border-border/40 px-5 py-3.5">
        <h2 className="font-display text-[15px] font-light tracking-quiet text-foreground/85">
          {meta.title}
        </h2>
        <span className="text-[11px] tracking-quiet text-faint">{meta.sub}</span>
      </header>
      <div
        key={tab}
        className="scroll-quiet animate-fade-in min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-5"
      >
        {tab === 'status' && <StatusTab />}
        {tab === 'config' && <ConfigTab />}
        {tab === 'logs' && <LogsTab />}
        {tab === 'wechat' && <WechatTab />}
      </div>
    </section>
  )
}
