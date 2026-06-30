import { cn } from '@/lib/utils'
import { formatTime } from '@/lib/format'
import type { ChatMessage } from '@/lib/console-types'

export function MessageBubble({ message }: { message: ChatMessage }) {
  const time = formatTime(message.created_at)

  if (message.role === 'reminder') {
    return (
      <div className="animate-settle flex justify-center py-1">
        <div className="glass-2 max-w-[85%] rounded-full border border-[--color-ember]/25 px-3.5 py-1.5 text-center text-[11px] leading-relaxed tracking-quiet text-ember/90">
          {message.content}
          {time && <span className="ml-2 text-faint">{time}</span>}
        </div>
      </div>
    )
  }

  const isUser = message.role === 'user'
  return (
    <div className={cn('animate-settle flex', isUser ? 'justify-end' : 'justify-start')}>
      <div className={cn('flex max-w-[82%] flex-col gap-1', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed tracking-quiet',
            isUser
              ? 'rounded-br-sm bg-secondary text-foreground/90'
              : 'glass rounded-bl-sm border border-border/60 text-foreground/85',
          )}
        >
          <p className="whitespace-pre-wrap text-pretty">{message.content}</p>
        </div>
        <span className="px-1 font-mono text-[10px] text-faint">
          {isUser ? '我' : 'xMe'}
          {time && ` · ${time}`}
        </span>
      </div>
    </div>
  )
}
