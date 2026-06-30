'use client'

import { useEffect, useRef, useState } from 'react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { MessageBubble } from './message-bubble'
import { MessageInput } from './message-input'
import { QuickActions } from './quick-actions'
import { InsightActions } from '../insights/insight-actions'

export function ChatPanel() {
  const { messages, messagesLoaded, sending, send } = useConsole()
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputAnchor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, sending])

  const handlePick = (prefill: string) => {
    setDraft((d) => (d ? `${d} ${prefill}` : prefill))
    inputAnchor.current
      ?.querySelector('textarea')
      ?.focus()
  }

  return (
    <section
      aria-label="对话"
      className="glass flex min-h-0 flex-1 flex-col rounded-2xl border border-border/50"
    >
      <header className="flex items-center justify-between border-b border-border/40 px-5 py-3.5">
        <div className="flex flex-col">
          <h2 className="font-display text-[15px] font-light tracking-quiet text-foreground/85">
            对话
          </h2>
          <span className="text-[11px] tracking-quiet text-faint">
            与记忆轻声交谈
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-faint">
            {messages.length > 0 ? `${messages.length} 条` : ''}
          </span>
          <InsightActions messages={messages} />
        </div>
      </header>

      <div
        ref={scrollRef}
        className="scroll-quiet flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-5 md:px-5"
      >
        {messages.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <EmptyState
              variant="signal"
              title={messagesLoaded ? '这里还没有回声' : '正在拾取记忆……'}
              hint={
                messagesLoaded
                  ? '说点什么，或让它记住一件小事。它会安静地待在这里。'
                  : undefined
              }
            />
          </div>
        ) : (
          messages.map((m, i) => <MessageBubble key={m.id ? `${m.id}-${i}` : i} message={m} />)
        )}
        {sending && (
          <div className="flex justify-start">
            <div className="glass flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-border/60 px-4 py-3">
              <Dot delay="0s" />
              <Dot delay="0.25s" />
              <Dot delay="0.5s" />
            </div>
          </div>
        )}
      </div>

      <div ref={inputAnchor} className="flex flex-col gap-2.5 border-t border-border/40 p-4">
        <QuickActions onPick={handlePick} />
        <MessageInput
          value={draft}
          onChange={setDraft}
          sending={sending}
          onSend={(text) => {
            send(text)
            setDraft('')
          }}
        />
      </div>
    </section>
  )
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="animate-pulse-slow h-1.5 w-1.5 rounded-full bg-faint"
      style={{ animationDelay: delay }}
    />
  )
}
