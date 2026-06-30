'use client'

import { useConsole } from './console-provider'
import { ConnPill } from './status-dot'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'

export function TopBar() {
  const { status, sse } = useConsole()
  const c = status?.connections

  const sseLabel = sse === 'open' ? '实时' : sse === 'connecting' ? '接入中' : '已断开'

  return (
    <header className="glass sticky top-0 z-30 flex items-center justify-between gap-4 border-b border-border/50 px-4 py-3 md:px-6">
      <div className="flex items-baseline gap-3">
        <span className="font-display text-lg font-light italic tracking-quiet text-foreground/90">
          xMe
        </span>
        <span className="hidden text-[11px] tracking-wide-quiet text-faint sm:inline">
          记忆控制台
        </span>
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 md:flex">
          <ConnPill label="qdrant" state={c?.qdrant ?? 'connecting'} />
          <ConnPill label="neo4j" state={c?.neo4j ?? 'connecting'} />
          <ConnPill label="llm" state={c?.llm ?? 'connecting'} />
        </div>

        {/* 移动端折叠为简短状态 */}
        <div className="flex items-center gap-2 md:hidden">
          <ConnPill label="llm" state={c?.llm ?? 'connecting'} />
        </div>

        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border border-border/50 px-2.5 py-1 text-[11px] tracking-quiet',
            sse === 'open' ? 'text-signal' : 'text-faint',
          )}
          title={`运行 ${formatDuration(status?.uptime)}`}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              sse === 'open' ? 'animate-pulse-slow bg-signal' : 'bg-faint',
            )}
          />
          {sseLabel}
        </span>
      </div>
    </header>
  )
}
