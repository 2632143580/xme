'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { CheckCircle2, Loader2, Plug, XCircle } from 'lucide-react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { cn } from '@/lib/utils'
import type { ConfigField } from '@/lib/console-types'

/* ── LLM provider tab defs ── */
const PROVIDER_TABS = [
  { key: 'volcengine', label: '火山引擎', prefix: 'VOLCENGINE_' },
  { key: 'deepseek', label: 'DeepSeek', prefix: 'DEEPSEEK_' },
  { key: 'openai', label: 'OpenAI', prefix: 'OPENAI_' },
] as const

/* ── Scheduler field keys for sub-grid ── */
const SCHED_ROWS: (readonly string[])[] = [
  ['ENABLE_SCHEDULER', 'IDLE_THRESHOLD_MINUTES'],
  ['SCHEDULER_TIMEZONE', 'SCHEDULER_MAX_WORKERS'],
  ['MORNING_GREETING_HOUR', 'MORNING_GREETING_MINUTE', 'MORNING_GREETING_MISFIRE_GRACE'],
  ['SCHEDULER_JOBS_DB', 'SCHEDULER_MONITORING'],
]

/* ── Internal: single field row (label left, input right) ── */
function FieldRow({
  field,
  value,
  onChange,
  className,
}: {
  field: ConfigField
  value: string
  onChange: (v: string) => void
  className?: string
}) {
  const inputType =
    field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'

  return (
    <label
      className={cn(
        'flex items-center gap-2 border-b border-border/30 px-3 py-2 last:border-b-0',
        className,
      )}
      title={field.hint}
    >
      <span className="w-[72px] shrink-0 text-[11px] tracking-quiet text-foreground/60 truncate">
        {field.label}
      </span>
      <input
        type={inputType}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 min-w-0 rounded-md border border-border/40 bg-background/30 px-2 py-1.5 font-mono text-[12px] text-foreground/80 outline-none transition-colors duration-300 placeholder:text-faint/60 focus:border-signal-dim/50"
        placeholder={field.hint}
      />
    </label>
  )
}

/* ── Main ── */
export function ConfigTab() {
  const {
    config,
    configLoaded,
    savingConfig,
    saveConfig,
    runTest,
    testing,
    testResult,
  } = useConsole()

  const [drafts, setDrafts] = useState<Record<string, string>>({})

  // init drafts from backend
  useEffect(() => {
    if (!config?.groups) return
    const init: Record<string, string> = {}
    for (const g of config.groups) for (const f of g.fields) init[f.key] = f.value
    setDrafts(init)
  }, [config])

  const changed = useMemo(() => {
    if (!config?.groups) return {}
    const out: Record<string, string> = {}
    for (const g of config.groups)
      for (const f of g.fields)
        if (drafts[f.key] !== undefined && drafts[f.key] !== f.value) out[f.key] = drafts[f.key]
    return out
  }, [config, drafts])

  const dirty = Object.keys(changed).length > 0

  // ── group lookups ──
  const llmGroup = config?.groups.find((g) => g.group === 'llm')
  const scheduleGroup = config?.groups.find((g) => g.group === 'schedule')
  const storageGroup = config?.groups.find((g) => g.group === 'storage')

  // ── LLM sub-grouping ──
  const llmParts = useMemo(() => {
    if (!llmGroup) return { common: [] as ConfigField[], providerFields: {} as Record<string, ConfigField[]> }
    const fields = llmGroup.fields
    const common = fields.filter((f) => f.key === 'LLM_PROVIDER' || f.key === 'MODEL_NAME')
    const providerFields: Record<string, ConfigField[]> = {}
    for (const { key, prefix } of PROVIDER_TABS) {
      providerFields[key] = fields.filter((f) => f.key.startsWith(prefix))
    }
    return { common, providerFields }
  }, [llmGroup])

  const activeProvider =
    PROVIDER_TABS.find((t) => t.key === (drafts['LLM_PROVIDER'] || '').toLowerCase())?.key ??
    'volcengine'

  const setDraftKey = (key: string) => (v: string) =>
    setDrafts((d) => ({ ...d, [key]: v }))

  // ── scheduler field map ──
  const schedMap = useMemo(() => {
    if (!scheduleGroup) return {} as Record<string, ConfigField>
    return Object.fromEntries(scheduleGroup.fields.map((f) => [f.key, f]))
  }, [scheduleGroup])

  // rest of schedule fields (not in SCHED_ROWS)
  const schedRest = useMemo(() => {
    if (!scheduleGroup) return [] as ConfigField[]
    const inRows = new Set(SCHED_ROWS.flat())
    return scheduleGroup.fields.filter((f) => !inRows.has(f.key))
  }, [scheduleGroup])

  /* ── empty state ── */
  if (!config?.groups?.length) {
    return (
      <EmptyState
        variant="wave"
        title={configLoaded ? '配置尚未就绪' : '正在读取配置……'}
        hint={configLoaded ? '与后端建立连接后，这里会显示可调的参数。' : undefined}
      />
    )
  }

  /* ── render ── */
  return (
    <div className="flex flex-col gap-4">
      {/* ═══ sticky action bar ═══ */}
      <div className="sticky top-0 z-10 -mx-1 flex items-center justify-between gap-3 rounded-xl border border-border/40 bg-background/85 px-4 py-2.5 backdrop-blur-md">
        <span className={cn('text-xs tracking-quiet', dirty ? 'text-signal' : 'text-faint')}>
          {dirty ? `${Object.keys(changed).length} 项待保存` : '已是最新'}
        </span>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => saveConfig(changed)}
            disabled={!dirty || savingConfig}
            className={cn(
              'lift inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs tracking-quiet transition-colors',
              dirty
                ? 'border-signal-dim/50 text-signal'
                : 'border-border/50 text-faint',
              'disabled:opacity-50 disabled:hover:translate-y-0',
            )}
          >
            {savingConfig && <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />}
            {savingConfig ? '保存中' : dirty ? `保存修改 · ${Object.keys(changed).length}` : '已是最新'}
          </button>

          <button
            type="button"
            onClick={runTest}
            disabled={testing}
            className="lift glass-2 inline-flex items-center gap-1.5 rounded-lg border border-border/50 px-3 py-1.5 text-xs tracking-quiet text-muted-foreground hover:text-foreground/80 disabled:opacity-50 disabled:hover:translate-y-0"
          >
            {testing ? (
              <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
            ) : (
              <Plug className="h-3 w-3" strokeWidth={1.5} />
            )}
            测试连接
          </button>

          {testResult && (
            <span
              className={cn(
                'inline-flex items-center gap-1 text-[11px] tracking-quiet',
                testResult.ok ? 'text-ok' : 'text-destructive',
              )}
            >
              {testResult.ok ? (
                <CheckCircle2 className="h-3 w-3" strokeWidth={1.5} />
              ) : (
                <XCircle className="h-3 w-3" strokeWidth={1.5} />
              )}
              {testResult.text}
            </span>
          )}
        </div>
      </div>

      {/* ═══ three-column grid ═══ */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {/* ── LLM ── */}
        <ConfigCard title="大语言模型">
          {/* provider tabs */}
          <div className="flex border-b border-border/30">
            {PROVIDER_TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setDrafts((d) => ({ ...d, LLM_PROVIDER: t.key }))}
                className={cn(
                  'flex-1 px-2 py-2 text-[12px] tracking-quiet border-b-2 -mb-px transition-colors duration-300',
                  activeProvider === t.key
                    ? 'border-signal text-signal'
                    : 'border-transparent text-faint hover:text-foreground/60',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* provider fields */}
          {llmParts.providerFields[activeProvider]?.map((f) => (
            <FieldRow key={f.key} field={f} value={drafts[f.key] ?? ''} onChange={setDraftKey(f.key)} />
          ))}

          {/* common fields (LLM_PROVIDER hidden, MODEL_NAME if exists) */}
          {llmParts.common
            .filter((f) => f.key !== 'LLM_PROVIDER')
            .map((f) => (
              <FieldRow key={f.key} field={f} value={drafts[f.key] ?? ''} onChange={setDraftKey(f.key)} />
            ))}

          {llmParts.providerFields[activeProvider]?.length === 0 &&
            llmParts.common.filter((f) => f.key !== 'LLM_PROVIDER').length === 0 && (
              <div className="px-3 py-4 text-center text-[11px] text-faint tracking-quiet">
                无配置项
              </div>
            )}
        </ConfigCard>

        {/* ── Storage ── */}
        <ConfigCard title="存储与向量">
          {storageGroup?.fields.length ? (
            storageGroup.fields.map((f) => (
              <FieldRow key={f.key} field={f} value={drafts[f.key] ?? ''} onChange={setDraftKey(f.key)} />
            ))
          ) : (
            <div className="px-3 py-4 text-center text-[11px] text-faint tracking-quiet">
              暂未连接
            </div>
          )}
        </ConfigCard>

        {/* ── Scheduler ── */}
        <ConfigCard title="主动调度">
          {/* sub-grid rows */}
          {SCHED_ROWS.map((keys, ri) => {
            const fields = keys.map((k) => schedMap[k]).filter(Boolean)
            if (fields.length === 0) return null
            return (
              <div
                key={ri}
                className={cn(
                  'grid gap-px border-b border-border/30 last:border-b-0',
                  fields.length === 4 && 'grid-cols-4',
                  fields.length === 3 && 'grid-cols-3',
                  fields.length === 2 && 'grid-cols-2',
                  fields.length === 1 && 'grid-cols-1',
                )}
              >
                {fields.map((f) => (
                  <label
                    key={f.key}
                    className="flex items-center gap-1.5 px-2.5 py-2"
                    title={f.hint}
                  >
                    <span className="w-16 shrink-0 text-[11px] tracking-quiet text-foreground/60 truncate">
                      {f.label}
                    </span>
                    <input
                      type={
                        f.type === 'password'
                          ? 'password'
                          : f.type === 'number'
                            ? 'number'
                            : 'text'
                      }
                      value={drafts[f.key] ?? ''}
                      onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                      className="flex-1 min-w-0 rounded-md border border-border/40 bg-background/30 px-2 py-1 font-mono text-[12px] text-foreground/75 outline-none transition-colors duration-300 placeholder:text-faint/50 focus:border-signal-dim/50"
                      placeholder={f.hint}
                    />
                  </label>
                ))}
              </div>
            )
          })}

          {/* remaining scheduler fields */}
          {schedRest.map((f) => (
            <FieldRow key={f.key} field={f} value={drafts[f.key] ?? ''} onChange={setDraftKey(f.key)} />
          ))}

          {scheduleGroup?.fields.length === 0 && (
            <div className="px-3 py-4 text-center text-[11px] text-faint tracking-quiet">
              调度器未启用
            </div>
          )}
        </ConfigCard>
      </div>
    </div>
  )
}

/* ── Card wrapper ── */
function ConfigCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col">
      <h3 className="mb-2 text-[11px] tracking-wide-quiet text-muted-foreground">{title}</h3>
      <div className="glass-2 flex flex-col divide-y-0 rounded-xl border border-border/50 overflow-hidden flex-1">
        {children}
      </div>
    </section>
  )
}
