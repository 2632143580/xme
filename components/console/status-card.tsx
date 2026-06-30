import { cn } from '@/lib/utils'

// 状态卡片：哑光毛玻璃 + 顶部渐变装饰线。悬停仅极轻微浮起，无发光、无色彩跳变。
export function StatusCard({
  label,
  value,
  unit,
  accent = 'cool',
}: {
  label: string
  value: string
  unit?: string
  accent?: 'cool' | 'warm'
}) {
  return (
    <div className="lift glass-2 relative overflow-hidden rounded-xl border border-border/50 p-4 hover:border-border">
      <span
        aria-hidden
        className={cn(
          'absolute inset-x-0 top-0 h-px',
          accent === 'cool'
            ? 'bg-gradient-to-r from-transparent via-signal-dim/60 to-transparent'
            : 'bg-gradient-to-r from-transparent via-[--color-ember]/40 to-transparent',
        )}
      />
      <p className="text-[11px] tracking-wide-quiet text-faint">{label}</p>
      <p className="mt-2 flex items-baseline gap-1">
        <span className="font-mono text-2xl font-light tabular-nums text-foreground/90">
          {value}
        </span>
        {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
      </p>
    </div>
  )
}
