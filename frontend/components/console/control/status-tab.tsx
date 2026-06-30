'use client'

import { Trash2 } from 'lucide-react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { StatusCard } from '../status-card'
import { formatClock, formatCount, formatDuration } from '@/lib/format'

export function StatusTab() {
  const { status, statusLoaded, reminders, removeReminder } = useConsole()
  const s = status

  return (
    <div className="flex flex-col gap-7">
      <section className="space-y-3">
        <SectionTitle title="此刻" sub="系统的呼吸与体量" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatusCard label="对话" value={formatCount(s?.stats.dialogues)} unit="条" />
          <StatusCard label="笔记" value={formatCount(s?.stats.notes)} unit="则" />
          <StatusCard label="向量" value={formatCount(s?.stats.vectors)} unit="维" />
          <StatusCard
            label="运行时长"
            value={s?.uptime != null ? formatDuration(s.uptime) : '—'}
          />
          <StatusCard
            label="空闲"
            value={s?.idle != null ? formatDuration(s.idle) : '—'}
            accent="warm"
          />
          <StatusCard label="状态" value={s?.running ? '在场' : '沉睡'} accent="warm" />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle title="知识图谱" sub="它如何理解你" />
        <div className="grid grid-cols-3 gap-3">
          <StatusCard label="偏好" value={formatCount(s?.graph.preferences)} />
          <StatusCard label="事件" value={formatCount(s?.graph.events)} />
          <StatusCard label="人物" value={formatCount(s?.graph.people)} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle
          title="待触发提醒"
          sub={reminders.length ? `${reminders.length} 项等待中` : '无'}
        />
        {reminders.length === 0 ? (
          <EmptyState
            variant="orbit"
            title={statusLoaded ? '没有待办的低语' : '正在聆听……'}
            hint={statusLoaded ? '一切都还安静，没有需要被记起的时刻。' : undefined}
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {reminders.map((r) => (
              <li
                key={r.job_id}
                className="lift glass-2 flex items-center justify-between gap-3 rounded-xl border border-border/50 px-4 py-3 hover:border-border"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm tracking-quiet text-foreground/85">
                    {r.content}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-faint">
                    {formatClock(r.trigger_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeReminder(r.job_id)}
                  aria-label="删除提醒"
                  className="shrink-0 rounded-lg p-1.5 text-faint transition-colors duration-500 hover:bg-secondary hover:text-foreground/70"
                >
                  <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function SectionTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <h3 className="text-xs tracking-wide-quiet text-muted-foreground">{title}</h3>
      {sub && <span className="text-[11px] tracking-quiet text-faint">{sub}</span>}
    </div>
  )
}
