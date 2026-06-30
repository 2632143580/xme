'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { sseUrl } from '@/lib/api'
import * as svc from '@/lib/services'
import type {
  ChatMessage,
  ConfigData,
  ConnState,
  LogEntry,
  Reminder,
  SystemStatus,
  WxMessage,
  WxStatus,
} from '@/lib/console-types'

export type SseState = 'connecting' | 'open' | 'closed'

export interface Toast {
  id: string
  tone: 'info' | 'error'
  text: string
}

interface ConsoleState {
  sse: SseState
  status: SystemStatus | null
  statusLoaded: boolean
  reminders: Reminder[]
  messages: ChatMessage[]
  messagesLoaded: boolean
  sending: boolean
  logs: LogEntry[]
  logsLoaded: boolean
  config: ConfigData | null
  configLoaded: boolean
  savingConfig: boolean
  needRestart: boolean
  testResult: { ok: boolean; text: string } | null
  testing: boolean
  wx: WxStatus | null
  wxLoaded: boolean
  wxMessages: WxMessage[]
  toasts: Toast[]
  // actions
  send: (text: string) => Promise<void>
  saveConfig: (changed: Record<string, string>) => Promise<void>
  runTest: () => Promise<void>
  removeReminder: (jobId: string) => Promise<void>
  refreshWx: () => Promise<void>
  sendWx: (to: string, content: string) => Promise<void>
  dismissToast: (id: string) => void
  dismissRestart: () => void
}

const Ctx = createContext<ConsoleState | null>(null)

const DEFAULT_CONN: ConnState = 'connecting'
const emptyStatus = (): SystemStatus => ({
  running: false,
  connections: { qdrant: DEFAULT_CONN, neo4j: DEFAULT_CONN, llm: DEFAULT_CONN },
  stats: { dialogues: 0, notes: 0, vectors: 0 },
  graph: { preferences: 0, events: 0, people: 0 },
})

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

const MAX_LOGS = 200
const MAX_MESSAGES = 120

export function ConsoleProvider({ children }: { children: React.ReactNode }) {
  const [sse, setSse] = useState<SseState>('connecting')
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [statusLoaded, setStatusLoaded] = useState(false)
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [messagesLoaded, setMessagesLoaded] = useState(false)
  const [sending, setSending] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [logsLoaded, setLogsLoaded] = useState(false)
  const [config, setConfig] = useState<ConfigData | null>(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [savingConfig, setSavingConfig] = useState(false)
  const [needRestart, setNeedRestart] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const [wx, setWx] = useState<WxStatus | null>(null)
  const [wxLoaded, setWxLoaded] = useState(false)
  const [wxMessages, setWxMessages] = useState<WxMessage[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((tone: Toast['tone'], text: string) => {
    const id = uid()
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5200)
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const pushMessage = useCallback((m: ChatMessage) => {
    setMessages((prev) => [...prev, m].slice(-MAX_MESSAGES))
  }, [])

  const pushLog = useCallback((l: LogEntry) => {
    setLogs((prev) => [...prev, l].slice(-MAX_LOGS))
  }, [])

  // ---- 轮询：status (5s) + logs (5s) + reminders ----
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await svc.getStatus()
        if (alive) {
          setStatus(s)
          setStatusLoaded(true)
        }
      } catch {
        if (alive) {
          setStatus((prev) => {
            const base = prev ?? emptyStatus()
            return {
              ...base,
              running: false,
              connections: { qdrant: 'down', neo4j: 'down', llm: 'down' },
            }
          })
          setStatusLoaded(true)
        }
      }
    }
    tick()
    const t = setInterval(tick, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const l = await svc.getLogs(30)
        if (alive) {
          setLogs(l)
          setLogsLoaded(true)
        }
      } catch {
        if (alive) setLogsLoaded(true)
      }
    }
    tick()
    const t = setInterval(tick, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const r = await svc.getReminders()
        if (alive) setReminders(r)
      } catch {
        /* 静默：连接尚未建立 */
      }
    }
    tick()
    const t = setInterval(tick, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  // ---- 初始化：历史对话 + 配置 ----
  useEffect(() => {
    let alive = true
    svc
      .getDialogues(20)
      .then((d) => {
        if (alive) {
          setMessages(d)
          setMessagesLoaded(true)
        }
      })
      .catch(() => {
        if (alive) setMessagesLoaded(true)
      })
    svc
      .getConfig()
      .then((c) => {
        if (alive) {
          setConfig(c)
          setConfigLoaded(true)
        }
      })
      .catch(() => {
        if (alive) setConfigLoaded(true)
      })
    return () => {
      alive = false
    }
  }, [])

  // ---- SSE 长连接：dialogue / reminder / graph / log / config，断开 3s 重连 ----
  useEffect(() => {
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let closed = false

    const connect = () => {
      setSse('connecting')
      try {
        es = new EventSource(sseUrl('/api/events'))
      } catch {
        scheduleRetry()
        return
      }
      es.onopen = () => setSse('open')
      es.addEventListener('dialogue', (e) => {
        try {
          const d = JSON.parse((e as MessageEvent).data)
          pushMessage({
            id: uid(),
            role: 'assistant',
            content: d.content ?? '',
            created_at: d.created_at ?? new Date().toISOString(),
          })
        } catch {}
      })
      es.addEventListener('reminder', (e) => {
        try {
          const d = JSON.parse((e as MessageEvent).data)
          pushMessage({
            id: uid(),
            role: 'reminder',
            content: typeof d === 'string' ? d : d.content ?? '',
            created_at: new Date().toISOString(),
          })
        } catch {}
      })
      es.addEventListener('log', (e) => {
        try {
          const d = JSON.parse((e as MessageEvent).data)
          pushLog({
            id: uid(),
            level: d.level ?? 'info',
            message: d.message ?? '',
            timestamp: d.timestamp ?? new Date().toISOString(),
          })
        } catch {}
      })
      es.addEventListener('graph', () => {
        // 图谱更新：触发一次状态刷新
        svc.getStatus().then(setStatus).catch(() => {})
      })
      es.addEventListener('config', (e) => {
        try {
          const d = JSON.parse((e as MessageEvent).data)
          if (d.need_restart) setNeedRestart(true)
        } catch {}
      })
      es.onerror = () => {
        es?.close()
        scheduleRetry()
      }
    }

    const scheduleRetry = () => {
      if (closed) return
      setSse('closed')
      retry = setTimeout(connect, 3000)
    }

    connect()
    return () => {
      closed = true
      if (retry) clearTimeout(retry)
      es?.close()
    }
  }, [pushLog, pushMessage])

  // ---- 微信：状态 + 消息轮询（5s） ----
  const refreshWx = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([svc.wxStatus(), svc.wxMessages(50)])
      setWx(s)
      setWxMessages(m)
      setWxLoaded(true)
    } catch {
      setWxLoaded(true)
    }
  }, [])

  useEffect(() => {
    refreshWx()
    const t = setInterval(refreshWx, 5000)
    return () => clearInterval(t)
  }, [refreshWx])

  // ---- actions ----
  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      setSending(true)
      pushMessage({
        id: uid(),
        role: 'user',
        content: trimmed,
        created_at: new Date().toISOString(),
      })
      try {
        const reply = await svc.sendMessage(trimmed)
        if (reply && reply.content) {
          pushMessage({
            id: reply.id ?? uid(),
            role: 'assistant',
            content: reply.content,
            created_at: reply.created_at ?? new Date().toISOString(),
          })
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : '消息发送失败'
        pushMessage({
          id: uid(),
          role: 'reminder',
          content: `未送达 · ${msg}`,
          created_at: new Date().toISOString(),
        })
        toast('error', `消息未送达 · ${msg}`)
      } finally {
        setSending(false)
      }
    },
    [pushMessage, toast],
  )

  const saveConfig = useCallback(
    async (changed: Record<string, string>) => {
      setSavingConfig(true)
      try {
        const res = await svc.putConfig(changed)
        if (res?.need_restart) setNeedRestart(true)
        // 合并回本地配置
        setConfig((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            groups: prev.groups.map((g) => ({
              ...g,
              fields: g.fields.map((f) =>
                f.key in changed ? { ...f, value: changed[f.key] } : f,
              ),
            })),
          }
        })
        toast('info', '配置已保存')
      } catch (err) {
        const msg = err instanceof Error ? err.message : '保存失败'
        toast('error', `配置未保存 · ${msg}`)
      } finally {
        setSavingConfig(false)
      }
    },
    [toast],
  )

  const runTest = useCallback(async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await svc.testConnection()
      setTestResult({
        ok: r.ok,
        text: r.ok
          ? `连接正常${r.latency_ms ? ` · ${r.latency_ms}ms` : ''}`
          : r.message || '连接失败',
      })
    } catch (err) {
      const msg = err instanceof Error ? err.message : '连接失败'
      setTestResult({ ok: false, text: msg })
    } finally {
      setTesting(false)
    }
  }, [])

  const removeReminder = useCallback(
    async (jobId: string) => {
      const prev = reminders
      setReminders((r) => r.filter((x) => x.job_id !== jobId))
      try {
        await svc.deleteReminder(jobId)
      } catch (err) {
        setReminders(prev)
        const msg = err instanceof Error ? err.message : '删除失败'
        toast('error', `提醒未删除 · ${msg}`)
      }
    },
    [reminders, toast],
  )

  const sendWx = useCallback(
    async (to: string, content: string) => {
      try {
        await svc.wxSend(to, content)
        toast('info', '测试消息已发送')
        refreshWx()
      } catch (err) {
        const msg = err instanceof Error ? err.message : '发送失败'
        toast('error', `发送失败 · ${msg}`)
      }
    },
    [refreshWx, toast],
  )

  const value = useMemo<ConsoleState>(
    () => ({
      sse,
      status,
      statusLoaded,
      reminders,
      messages,
      messagesLoaded,
      sending,
      logs,
      logsLoaded,
      config,
      configLoaded,
      savingConfig,
      needRestart,
      testResult,
      testing,
      wx,
      wxLoaded,
      wxMessages,
      toasts,
      send,
      saveConfig,
      runTest,
      removeReminder,
      refreshWx,
      sendWx,
      dismissToast,
      dismissRestart: () => setNeedRestart(false),
    }),
    [
      sse,
      status,
      statusLoaded,
      reminders,
      messages,
      messagesLoaded,
      sending,
      logs,
      logsLoaded,
      config,
      configLoaded,
      savingConfig,
      needRestart,
      testResult,
      testing,
      wx,
      wxLoaded,
      wxMessages,
      toasts,
      send,
      saveConfig,
      runTest,
      removeReminder,
      refreshWx,
      sendWx,
      dismissToast,
    ],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useConsole() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useConsole 必须在 ConsoleProvider 内使用')
  return ctx
}
