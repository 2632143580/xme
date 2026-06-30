'use client'

import { BookMarked, Clock, Sparkles } from 'lucide-react'

const ACTIONS = [
  { icon: BookMarked, label: '记一下', prefill: '帮我记住：' },
  { icon: Sparkles, label: '回忆', prefill: '帮我回忆一下关于' },
  { icon: Clock, label: '提醒我', prefill: '提醒我' },
]

export function QuickActions({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {ACTIONS.map(({ icon: Icon, label, prefill }) => (
        <button
          key={label}
          type="button"
          onClick={() => onPick(prefill)}
          className="lift glass-2 inline-flex items-center gap-1.5 rounded-full border border-border/50 px-3 py-1.5 text-xs tracking-quiet text-muted-foreground hover:border-border hover:text-foreground/80"
        >
          <Icon className="h-3.5 w-3.5 text-faint" strokeWidth={1.5} />
          {label}
        </button>
      ))}
    </div>
  )
}
