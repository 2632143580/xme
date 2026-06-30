// API 调用层：每个接口一个函数，全部对接真实后端（见「前后端对接清单」）。
import { api } from './api'
import type {
  ChatMessage,
  ConfigData,
  ConfigField,
  ConfigGroup,
  LogEntry,
  Reminder,
  SystemStatus,
  WxLoginResponse,
  WxMessage,
  WxStatus,
} from './console-types'

// 系统状态
export const getStatus = () => api.get<SystemStatus>('/api/status')

// ── 配置 ────────────────────────────────────────────────────

// 后端返回的扁平 config 项
interface RawConfigItem {
  value: string | number | boolean
  raw_type: string
  hot_update: boolean
}

/** 将扁平 config dict 转为前端分组的 ConfigData */
function formatConfigData(raw: Record<string, RawConfigItem>): ConfigData {
  // 友好的字段标签
  const LABELS: Record<string, string> = {
    LLM_PROVIDER: 'LLM 供应商',
    VOLCENGINE_API_KEY: '火山引擎 API Key',
    VOLCENGINE_BASE_URL: '火山引擎 API 地址',
    VOLCENGINE_MODEL: '火山引擎模型',
    DEEPSEEK_API_KEY: 'DeepSeek API Key',
    DEEPSEEK_BASE_URL: 'DeepSeek API 地址',
    DEEPSEEK_MODEL: 'DeepSeek 模型',
    OPENAI_API_KEY: 'OpenAI API Key',
    OPENAI_BASE_URL: 'OpenAI API 地址',
    MODEL_NAME: '模型名称（旧格式）',
    SQLITE_PATH: 'SQLite 数据库路径',
    QDRANT_HOST: 'Qdrant 主机',
    QDRANT_PORT: 'Qdrant 端口',
    NEO4J_URI: 'Neo4j URI',
    NEO4J_USER: 'Neo4j 用户名',
    NEO4J_PASSWORD: 'Neo4j 密码',
    EMBEDDING_MODEL: '向量模型',
    BGE_M3_DIR: 'BGE-M3 模型目录',
    ENABLE_SCHEDULER: '启用调度器',
    IDLE_THRESHOLD_MINUTES: '空闲阈值（分钟）',
    SCHEDULER_TIMEZONE: '调度器时区',
    SCHEDULER_MAX_WORKERS: '最大工作线程',
    SCHEDULER_COALESCE: '调度合并',
    SCHEDULER_MAX_INSTANCES: '最大实例数',
    SCHEDULER_JOBS_DB: '作业数据库路径',
    SCHEDULER_MONITORING: '调度监控',
    MORNING_GREETING_HOUR: '早安问候（时）',
    MORNING_GREETING_MINUTE: '早安问候（分）',
    MORNING_GREETING_MISFIRE_GRACE: '早安宽限期（秒）',
    REMINDER_MISFIRE_GRACE: '提醒宽限期（秒）',
    WX_BASE_URL: '微信 API 地址',
    WX_BOT_TYPE: '微信 Bot 类型',
    WX_POLL_TIMEOUT: '微信轮询超时（秒）',
    WX_MAX_CONCURRENT: '微信最大并发',
    WX_CHANNEL_VERSION: '微信通道版本',
    API_PORT: 'API 端口',
  }

  // 字段提示
  const HINTS: Record<string, string> = {
    LLM_PROVIDER: 'volcengine / deepseek / openai',
    MODEL_NAME: '仅旧格式使用',
    WX_BOT_TYPE: 'bot 类型编号',
  }

  // 需要密码类型的字段（API Key）
  const PASSWORD_KEYS = new Set([
    'VOLCENGINE_API_KEY', 'DEEPSEEK_API_KEY',
    'OPENAI_API_KEY', 'NEO4J_PASSWORD',
  ])

  // 需要数字类型的字段
  const NUMBER_KEYS = new Set([
    'QDRANT_PORT', 'IDLE_THRESHOLD_MINUTES', 'SCHEDULER_MAX_WORKERS',
    'SCHEDULER_MAX_INSTANCES', 'MORNING_GREETING_HOUR', 'MORNING_GREETING_MINUTE',
    'MORNING_GREETING_MISFIRE_GRACE', 'REMINDER_MISFIRE_GRACE',
    'WX_POLL_TIMEOUT', 'WX_MAX_CONCURRENT', 'API_PORT',
  ])

  // 将 env var key 映射到分组
  const groupOf = (key: string): string => {
    if (key === 'LLM_PROVIDER' || key.startsWith('VOLCENGINE_') || key.startsWith('DEEPSEEK_') || key.startsWith('OPENAI_') || key === 'MODEL_NAME') return 'llm'
    if (key.startsWith('SCHEDULER_') || key.startsWith('MORNING_') || key.startsWith('REMINDER_') || key === 'ENABLE_SCHEDULER' || key === 'IDLE_THRESHOLD_MINUTES') return 'schedule'
    if (key.startsWith('QDRANT_') || key.startsWith('NEO4J_') || key === 'SQLITE_PATH' || key === 'EMBEDDING_MODEL' || key === 'BGE_M3_DIR') return 'storage'
    return '__ungrouped__'
  }

  const groupLabels: Record<string, { group: ConfigGroup['group']; title: string }> = {
    llm: { group: 'llm', title: '大语言模型' },
    schedule: { group: 'schedule', title: '主动调度' },
    storage: { group: 'storage', title: '存储与向量' },
  }

  // 构建分组
  const groups = new Map<string, ConfigField[]>()

  for (const [envKey, item] of Object.entries(raw)) {
    const g = groupOf(envKey)
    if (!groups.has(g)) groups.set(g, [])

    let fieldType: ConfigField['type'] = undefined
    if (PASSWORD_KEYS.has(envKey)) fieldType = 'password'
    else if (NUMBER_KEYS.has(envKey)) fieldType = 'number'

    groups.get(g)!.push({
      key: envKey,
      label: LABELS[envKey] ?? envKey,
      value: String(item.value),
      type: fieldType,
      hint: HINTS[envKey],
    })
  }

  const result: ConfigData = { groups: [] }

  for (const [g, fields] of groups) {
    const meta = groupLabels[g]
    if (meta) {
      result.groups.push({ ...meta, fields })
    }
  }

  return result
}

export const getConfig = async () => {
  const raw = await api.get<Record<string, RawConfigItem>>('/api/config')
  return formatConfigData(raw)
}
export const putConfig = (changed: Record<string, string>) =>
  api.put<{ updated: string[]; need_restart: boolean }>('/api/config', changed)
export const testConnection = () =>
  api.post<{ ok: boolean; latency_ms?: number; message?: string }>('/api/test-connection')

// 对话
export const getDialogues = (limit = 20) =>
  api.get<ChatMessage[]>(`/api/dialogues?limit=${limit}`)
export const sendMessage = (content: string) =>
  api.post<ChatMessage>('/api/message', { content })

// 提醒
export const getReminders = () => api.get<Reminder[]>('/api/reminders')
export const deleteReminder = (jobId: string) =>
  api.del<void>(`/api/reminders/${jobId}`)

// 日志
export const getLogs = (limit = 30) =>
  api.get<LogEntry[]>(`/api/logs?limit=${limit}`)

// 微信
export const wxLogin = () => api.post<WxLoginResponse>('/api/weixin/login')
export const wxLoginStatus = (eventId: string) =>
  api.get<{ state: string }>(`/api/weixin/login-status?event_id=${eventId}`)
export const wxStatus = () => api.get<WxStatus>('/api/weixin/status')
export const wxMessages = (limit = 50) =>
  api.get<WxMessage[]>(`/api/weixin/messages?limit=${limit}`)
export const wxSend = (to: string, content: string) =>
  api.post<{ ok: boolean }>('/api/weixin/send', { to, content })