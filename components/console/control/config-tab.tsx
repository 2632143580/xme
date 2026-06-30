'use client'

import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Loader2, Plug, XCircle } from 'lucide-react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { cn } from '@/lib/utils'

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

  // 用后端值初始化草稿
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
        if (drafts[f.key] !== undefined && drafts[f.key] !== f.value)
          out[f.key] = drafts[f.key]
    return out
  }, [config, drafts])

  const dirty = Object.keys(changed).length > 0

  if (!config?.groups?.length) {
    return (
      <EmptyState
        variant="wave"
        title={configLoaded ? '配置尚未就绪' : '正在读取配置……'}
        hint={configLoaded ? '与后端建立连接后，这里会显示可调的参数。' : undefined}
      />
    )
  }

  return (
    <div className="flex flex-col gap-7">
      {config.groups.map((group) => (
        <section key={group.group} className="space-y-3">
          <h3 className="text-xs tracking-wide-quiet text-muted-foreground">
            {group.title}
          </h3>
          <div className="glass-2 flex flex-col divide-y divide-border/40 rounded-xl border border-border/50">
            {group.fields.map((f) => (
              <label key={f.key} className="flex flex-col gap-1.5 px-4 py-3.5">
                <span className="text-[13px] tracking-quiet text-foreground/80">
                  {f.label}
                </span>
                <input
                  type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'}
                  value={drafts[f.key] ?? ''}
                  onChange={(e) =>
                    setDrafts((d) => ({ ...d, [f.key]: e.target.value }))
                  }
                  className="w-full rounded-lg border border-border/50 bg-background/40 px-3 py-2 font-mono text-[13px] text-foreground/85 outline-none transition-colors duration-500 placeholder:text-faint focus:border-signal-dim/60"
                  placeholder={f.hint}
                />
                {f.hint && (
                  <span className="text-[11px] tracking-quiet text-faint">{f.hint}</span>
                )}
              </label>
            ))}
          </div>
        </section>
      ))}

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <button
          type="button"
          onClick={() => saveConfig(changed)}
          disabled={!dirty || savingConfig}
          className={cn(
            'lift inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm tracking-quiet',
            dirty
              ? 'border-signal-dim/50 text-signal'
              : 'border-border/50 text-faint',
            'disabled:opacity-50 disabled:hover:translate-y-0',
          )}
        >
          {savingConfig && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />}
          {savingConfig ? '保存中' : dirty ? `保存修改 · ${Object.keys(changed).length}` : '已是最新'}
        </button>

        <button
          type="button"
          onClick={runTest}
          disabled={testing}
          className="lift glass-2 inline-flex items-center gap-2 rounded-xl border border-border/50 px-4 py-2 text-sm tracking-quiet text-muted-foreground hover:text-foreground/80 disabled:opacity-50 disabled:hover:translate-y-0"
        >
          {testing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
          ) : (
            <Plug className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
          测试连接
        </button>

        {testResult && (
          <span
            className={cn(
              'inline-flex items-center gap-1.5 text-xs tracking-quiet',
              testResult.ok ? 'text-ok' : 'text-destructive',
            )}
          >
            {testResult.ok ? (
              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
            ) : (
              <XCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            {testResult.text}
          </span>
        )}
      </div>
    </div>
  )
}
