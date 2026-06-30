'use client'

import { useEffect, useRef } from 'react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { LogEntry } from '@/lib/console-types'

const LEVEL_TONE: Record<LogEntry['level'], string> = {
  info: 'text-muted-foreground',
  debug: 'text-faint',
  warn: 'text-warn',
  error: 'text-destructive',
}

export function LogsTab() {
  const { logs, logsLoaded } = useConsole()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [logs.length])

  if (logs.length === 0) {
    return (
      <EmptyState
        variant="wave"
        title={logsLoaded ? '日志一片静默' : '正在接入日志流……'}
        hint={logsLoaded ? '系统还没有想说的话。运行起来后，它的低语会出现在这里。' : undefined}
      />
    )
  }

  return (
    <div
      ref={ref}
      className="scroll-quiet glass-2 flex max-h-[60vh] flex-col gap-0.5 overflow-y-auto rounded-xl border border-border/50 p-3"
    >
      {logs.map((l) => (
        <div
          key={l.id}
          className="flex items-baseline gap-3 rounded-md px-2 py-1.5 font-mono text-[12px] leading-relaxed transition-colors duration-500 hover:bg-secondary/40"
        >
          <span className="shrink-0 text-faint">{formatTime(l.timestamp)}</span>
          <span className={cn('w-12 shrink-0 uppercase', LEVEL_TONE[l.level])}>
            {l.level}
          </span>
          <span className="min-w-0 break-words text-foreground/75">{l.message}</span>
        </div>
      ))}
    </div>
  )
}
