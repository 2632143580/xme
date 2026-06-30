'use client'

import { useEffect, useRef } from 'react'
import { ArrowUp } from 'lucide-react'
import { cn } from '@/lib/utils'

export function MessageInput({
  value,
  onChange,
  onSend,
  sending,
}: {
  value: string
  onChange: (v: string) => void
  onSend: (text: string) => void
  sending: boolean
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const text = value.trim()
    if (!text || sending) return
    onSend(text)
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [value])

  return (
    <div className="glass flex items-end gap-2 rounded-2xl border border-border/60 p-2 transition-colors duration-500 focus-within:border-signal-dim/60">
      <textarea
        ref={ref}
        value={value}
        rows={1}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKey}
        placeholder="写下此刻的念头，或交给它记住……"
        className="scroll-quiet max-h-[140px] flex-1 resize-none bg-transparent px-2.5 py-1.5 text-sm leading-relaxed tracking-quiet text-foreground/90 outline-none placeholder:text-faint"
        aria-label="对话输入"
      />
      <button
        type="button"
        onClick={submit}
        disabled={!value.trim() || sending}
        aria-label="发送"
        className={cn(
          'lift flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 text-foreground/70',
          'disabled:opacity-35 disabled:hover:translate-y-0',
          !!value.trim() && !sending && 'border-signal-dim/50 text-signal',
        )}
      >
        <ArrowUp className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  )
}
