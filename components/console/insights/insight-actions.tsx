'use client'

import { useEffect, useState } from 'react'
import { Cloud, Activity } from 'lucide-react'
import type { ChatMessage } from '@/lib/console-types'
import { hasWebGPU } from '@/lib/sentiment'
import { WordCloudDialog } from './word-cloud-dialog'
import { SentimentDialog } from './sentiment-dialog'

export function InsightActions({ messages }: { messages: ChatMessage[] }) {
  const [open, setOpen] = useState<'cloud' | 'sentiment' | null>(null)
  const [gpu, setGpu] = useState(false)

  // WebGPU 探测放在客户端（异步请求 adapter），避免 SSR 不一致与误判
  useEffect(() => {
    let alive = true
    hasWebGPU().then((ok) => {
      if (alive) setGpu(ok)
    })
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="flex items-center gap-1.5">
      <IconButton
        label="生成词云"
        onClick={() => setOpen('cloud')}
        icon={<Cloud className="h-4 w-4" strokeWidth={1.5} />}
      />
      {gpu && (
        <IconButton
          label="情绪分析"
          onClick={() => setOpen('sentiment')}
          icon={<Activity className="h-4 w-4" strokeWidth={1.5} />}
        />
      )}

      {open === 'cloud' && (
        <WordCloudDialog messages={messages} onClose={() => setOpen(null)} />
      )}
      {open === 'sentiment' && (
        <SentimentDialog messages={messages} onClose={() => setOpen(null)} />
      )}
    </div>
  )
}

function IconButton({
  label,
  onClick,
  icon,
}: {
  label: string
  onClick: () => void
  icon: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="lift glass-2 flex h-8 w-8 items-center justify-center rounded-full border border-border/50 text-muted-foreground hover:text-foreground/80"
    >
      {icon}
    </button>
  )
}
