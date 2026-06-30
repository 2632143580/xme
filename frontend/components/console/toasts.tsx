'use client'

import { RotateCcw, X } from 'lucide-react'
import { useConsole } from './console-provider'
import { cn } from '@/lib/utils'

export function Toasts() {
  const { toasts, dismissToast, needRestart, dismissRestart } = useConsole()

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-20 z-40 flex flex-col items-center gap-2 px-4 lg:bottom-6">
      {needRestart && (
        <div className="animate-settle glass pointer-events-auto flex items-center gap-3 rounded-xl border border-[--color-ember]/30 px-4 py-2.5">
          <RotateCcw className="h-4 w-4 text-ember" strokeWidth={1.5} />
          <span className="text-[13px] tracking-quiet text-foreground/80">
            部分配置需要重启后端方能生效
          </span>
          <button
            type="button"
            onClick={dismissRestart}
            aria-label="知道了"
            className="rounded-md p-1 text-faint transition-colors duration-500 hover:text-foreground/70"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      )}

      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'animate-settle glass pointer-events-auto flex items-center gap-3 rounded-xl border px-4 py-2.5',
            t.tone === 'error' ? 'border-destructive/30' : 'border-border/60',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              t.tone === 'error' ? 'bg-destructive' : 'bg-signal',
            )}
          />
          <span className="text-[13px] tracking-quiet text-foreground/80">{t.text}</span>
          <button
            type="button"
            onClick={() => dismissToast(t.id)}
            aria-label="关闭"
            className="rounded-md p-1 text-faint transition-colors duration-500 hover:text-foreground/70"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      ))}
    </div>
  )
}
