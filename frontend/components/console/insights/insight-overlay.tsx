'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface InsightOverlayProps {
  title: string
  subtitle?: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
}

export function InsightOverlay({ title, subtitle, onClose, children, footer }: InsightOverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // 焦点移入弹层，便于键盘操作
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {/* 背景：向中心微透，四角隐没 */}
      <button
        type="button"
        aria-label="关闭"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-background/70 backdrop-blur-sm"
        style={{
          background:
            'radial-gradient(circle at center, color-mix(in oklch, var(--background) 55%, transparent), color-mix(in oklch, var(--background) 88%, transparent))',
        }}
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="animate-settle glass relative flex max-h-[88dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border/60 outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-border/40 px-5 py-4">
          <div className="flex flex-col gap-0.5">
            <h2 className="font-display text-lg font-light tracking-quiet text-foreground/90">
              {title}
            </h2>
            {subtitle && (
              <p className="text-[12px] leading-relaxed tracking-quiet text-faint">{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="lift glass-2 -mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/50 text-muted-foreground hover:text-foreground/80"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </header>

        <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>

        {footer && (
          <footer className="border-t border-border/40 px-5 py-3.5">{footer}</footer>
        )}
      </div>
    </div>
  )
}

export type TimeRange = 'today' | 'week' | 'all'

export function RangeTabs({
  value,
  onChange,
}: {
  value: TimeRange
  onChange: (r: TimeRange) => void
}) {
  const opts: { key: TimeRange; label: string }[] = [
    { key: 'today', label: '今天' },
    { key: 'week', label: '本周' },
    { key: 'all', label: '全部' },
  ]
  return (
    <div className="inline-flex rounded-full border border-border/50 bg-surface/40 p-0.5">
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          aria-pressed={value === o.key}
          className={`rounded-full px-3 py-1 text-[12px] tracking-quiet transition-colors duration-500 ${
            value === o.key
              ? 'bg-secondary text-foreground/90'
              : 'text-faint hover:text-muted-foreground'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** 按时间范围筛选消息（纯函数，供两个功能复用） */
export function filterByRange<T extends { created_at: string }>(
  items: T[],
  range: TimeRange,
): T[] {
  if (range === 'all') return items
  const now = new Date()
  let start: number
  if (range === 'today') {
    const d = new Date(now)
    d.setHours(0, 0, 0, 0)
    start = d.getTime()
  } else {
    // 本周：最近 7 天
    start = now.getTime() - 7 * 24 * 60 * 60 * 1000
  }
  return items.filter((it) => {
    const t = new Date(it.created_at).getTime()
    return !Number.isNaN(t) && t >= start
  })
}
