// 与后端对接的类型定义（对应「前后端对接清单」）

export type ConnState = 'connected' | 'connecting' | 'down'

export interface SystemStatus {
  running: boolean
  bot_id?: string
  user_id?: string
  uptime?: number // 秒
  idle?: number // 空闲秒数
  connections: {
    qdrant: ConnState
    neo4j: ConnState
    llm: ConnState
  }
  stats: {
    dialogues: number
    notes: number
    vectors: number
  }
  graph: {
    preferences: number
    events: number
    people: number
  }
}

export interface Reminder {
  job_id: string
  content: string
  trigger_at: string // ISO
}

export type ChatRole = 'user' | 'assistant' | 'reminder'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  created_at: string // ISO
}

export interface LogEntry {
  id: string
  level: 'info' | 'warn' | 'error' | 'debug'
  message: string
  timestamp: string // ISO
}

export interface ConfigField {
  key: string
  label: string
  value: string
  type?: 'text' | 'password' | 'number'
  hint?: string
}

export interface ConfigGroup {
  group: 'llm' | 'schedule' | 'storage'
  title: string
  fields: ConfigField[]
}

export interface ConfigData {
  groups: ConfigGroup[]
  need_restart?: boolean
}

export type WxState = 'logged_out' | 'awaiting_scan' | 'logged_in' | 'error'

export interface WxStatus {
  state: WxState
  nickname?: string
  wxid?: string
}

export interface WxLoginResponse {
  event_id: string
  qrcode?: string // data url 或 url
}

export interface WxMessage {
  id: string
  from: string
  content: string
  created_at: string
  direction: 'in' | 'out'
}
