'use client'

import { Activity, MessagesSquare, ScrollText, SlidersHorizontal, Smartphone } from 'lucide-react'
import { cn } from '@/lib/utils'

export type NavKey = 'chat' | 'status' | 'config' | 'logs' | 'wechat'

const ITEMS: { key: NavKey; label: string; icon: typeof Activity }[] = [
  { key: 'chat', label: '对话', icon: MessagesSquare },
  { key: 'status', label: '状态', icon: Activity },
  { key: 'config', label: '配置', icon: SlidersHorizontal },
  { key: 'logs', label: '日志', icon: ScrollText },
  { key: 'wechat', label: '微信', icon: Smartphone },
]

export function SideNav({
  active,
  onSelect,
}: {
  active: NavKey
  onSelect: (key: NavKey) => void
}) {
  return (
    <nav
      aria-label="主导航"
      className={cn(
        // 移动端：底部横向；桌面：左侧纵向细栏
        'glass z-20 flex shrink-0 items-center gap-1 border-border/50',
        'fixed inset-x-0 bottom-0 justify-around border-t px-2 py-2',
        'lg:static lg:h-auto lg:flex-col lg:justify-start lg:gap-2 lg:border-r lg:border-t-0 lg:px-2 lg:py-5',
      )}
    >
      {ITEMS.map(({ key, label, icon: Icon }) => {
        const on = active === key
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelect(key)}
            aria-current={on ? 'page' : undefined}
            className={cn(
              'lift group relative flex flex-1 flex-col items-center gap-1 rounded-xl px-3 py-2 lg:flex-none lg:w-14',
              on ? 'text-signal' : 'text-faint hover:text-muted-foreground',
            )}
          >
            <span
              aria-hidden
              className={cn(
                'absolute rounded-full bg-signal transition-opacity duration-700',
                'left-1/2 top-0 h-px w-6 -translate-x-1/2 lg:left-0 lg:top-1/2 lg:h-6 lg:w-px lg:-translate-x-0 lg:-translate-y-1/2',
                on ? 'opacity-70' : 'opacity-0',
              )}
            />
            <Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
            <span className="text-[10px] tracking-quiet">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}
