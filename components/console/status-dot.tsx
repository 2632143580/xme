import { cn } from '@/lib/utils'
import type { ConnState } from '@/lib/console-types'

const TONE: Record<ConnState, string> = {
  connected: 'bg-ok',
  connecting: 'bg-warn',
  down: 'bg-faint',
}

export function StatusDot({ state, className }: { state: ConnState; className?: string }) {
  return (
    <span className={cn('relative inline-flex h-1.5 w-1.5', className)}>
      {state === 'connected' && (
        <span className="animate-pulse-slow absolute inset-0 rounded-full bg-ok blur-[3px]" />
      )}
      <span className={cn('relative inline-block h-1.5 w-1.5 rounded-full', TONE[state])} />
    </span>
  )
}

export function ConnPill({ label, state }: { label: string; state: ConnState }) {
  const text =
    state === 'connected' ? '在线' : state === 'connecting' ? '连接中' : '离线'
  return (
    <span className="glass-2 inline-flex items-center gap-2 rounded-full border border-border/60 px-2.5 py-1 text-[11px] tracking-quiet text-muted-foreground">
      <StatusDot state={state} />
      <span className="font-mono uppercase text-foreground/70">{label}</span>
      <span className="text-faint">{text}</span>
    </span>
  )
}
