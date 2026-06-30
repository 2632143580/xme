'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, QrCode, Send } from 'lucide-react'
import { useConsole } from '../console-provider'
import { EmptyState } from '../empty-state'
import { StatusDot } from '../status-dot'
import { formatTime } from '@/lib/format'
import { wxLogin, wxLoginStatus } from '@/lib/services'
import { cn } from '@/lib/utils'
import type { ConnState } from '@/lib/console-types'

export function WechatTab() {
  const { wx, wxLoaded, wxMessages, sendWx } = useConsole()
  const [qr, setQr] = useState<string | null>(null)
  const [loggingIn, setLoggingIn] = useState(false)
  const [loginHint, setLoginHint] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [to, setTo] = useState('')
  const [text, setText] = useState('')

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const startLogin = async () => {
    setLoggingIn(true)
    setLoginHint(null)
    setQr(null)
    try {
      const res = await wxLogin()
      if (res.qrcode) setQr(res.qrcode)
      setLoginHint('请使用微信扫描二维码')
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const st = await wxLoginStatus(res.event_id)
          if (st.state === 'logged_in') {
            setLoginHint('登录成功')
            setQr(null)
            if (pollRef.current) clearInterval(pollRef.current)
            setLoggingIn(false)
          } else if (st.state === 'error') {
            setLoginHint('登录失败，请重试')
            if (pollRef.current) clearInterval(pollRef.current)
            setLoggingIn(false)
          }
        } catch {
          /* 轮询静默失败，继续等待下一次 */
        }
      }, 2000)
    } catch (err) {
      setLoginHint(err instanceof Error ? err.message : '无法发起登录')
      setLoggingIn(false)
    }
  }

  const state = wx?.state ?? 'logged_out'
  const connState: ConnState =
    state === 'logged_in' ? 'connected' : state === 'awaiting_scan' ? 'connecting' : 'down'
  const stateText =
    state === 'logged_in'
      ? `已登录${wx?.nickname ? ` · ${wx.nickname}` : ''}`
      : state === 'awaiting_scan'
        ? '等待扫码'
        : state === 'error'
          ? '连接异常'
          : '未登录'

  return (
    <div className="flex flex-col gap-7">
      <section className="space-y-3">
        <h3 className="text-xs tracking-wide-quiet text-muted-foreground">连接状态</h3>
        <div className="glass-2 flex items-center justify-between rounded-xl border border-border/50 px-4 py-3.5">
          <div className="flex items-center gap-2.5">
            <StatusDot state={connState} />
            <span className="text-sm tracking-quiet text-foreground/85">{stateText}</span>
          </div>
          {wx?.wxid && (
            <span className="font-mono text-[11px] text-faint">{wx.wxid}</span>
          )}
        </div>
      </section>

      {state !== 'logged_in' && (
        <section className="space-y-3">
          <h3 className="text-xs tracking-wide-quiet text-muted-foreground">登录</h3>
          <div className="glass-2 flex flex-col items-center gap-4 rounded-xl border border-border/50 px-4 py-7">
            {qr ? (
              <div className="rounded-xl border border-border/60 bg-background/60 p-3">
                {/* 二维码由后端返回，可能是 data url 或图片地址 */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={qr} alt="微信登录二维码" className="h-44 w-44 rounded" />
              </div>
            ) : (
              <div className="flex h-44 w-44 items-center justify-center rounded-xl border border-dashed border-border/50">
                <QrCode className="h-10 w-10 text-faint" strokeWidth={1} />
              </div>
            )}
            {loginHint && (
              <p className="text-xs tracking-quiet text-muted-foreground">{loginHint}</p>
            )}
            <button
              type="button"
              onClick={startLogin}
              disabled={loggingIn}
              className="lift inline-flex items-center gap-2 rounded-xl border border-signal-dim/50 px-4 py-2 text-sm tracking-quiet text-signal disabled:opacity-50 disabled:hover:translate-y-0"
            >
              {loggingIn && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />}
              {loggingIn ? '等待扫码' : '获取登录二维码'}
            </button>
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h3 className="text-xs tracking-wide-quiet text-muted-foreground">发送测试消息</h3>
        <div className="glass-2 flex flex-col gap-2.5 rounded-xl border border-border/50 p-4">
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="接收者 wxid / 群聊名"
            className="w-full rounded-lg border border-border/50 bg-background/40 px-3 py-2 font-mono text-[13px] text-foreground/85 outline-none transition-colors duration-500 placeholder:text-faint focus:border-signal-dim/60"
          />
          <div className="flex items-end gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="消息内容"
              className="w-full flex-1 rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-[13px] text-foreground/85 outline-none transition-colors duration-500 placeholder:text-faint focus:border-signal-dim/60"
            />
            <button
              type="button"
              disabled={!to.trim() || !text.trim() || state !== 'logged_in'}
              onClick={() => {
                sendWx(to.trim(), text.trim())
                setText('')
              }}
              className={cn(
                'lift flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 text-foreground/70',
                'disabled:opacity-35 disabled:hover:translate-y-0',
              )}
              aria-label="发送测试消息"
            >
              <Send className="h-4 w-4" strokeWidth={1.5} />
            </button>
          </div>
          {state !== 'logged_in' && (
            <p className="text-[11px] tracking-quiet text-faint">登录后方可发送。</p>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs tracking-wide-quiet text-muted-foreground">近期消息</h3>
        {wxMessages.length === 0 ? (
          <EmptyState
            variant="orbit"
            title={wxLoaded ? '没有往来的消息' : '正在同步……'}
            hint={wxLoaded ? '当微信开始流动，这里会留下它们的痕迹。' : undefined}
          />
        ) : (
          <ul className="scroll-quiet flex max-h-[40vh] flex-col gap-2 overflow-y-auto">
            {wxMessages.map((m) => (
              <li
                key={m.id}
                className={cn(
                  'glass-2 rounded-xl border border-border/50 px-3.5 py-2.5',
                  m.direction === 'out' && 'border-signal-dim/30',
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-mono text-[11px] text-faint">
                    {m.direction === 'out' ? '→ ' : ''}
                    {m.from}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-faint">
                    {formatTime(m.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-[13px] leading-relaxed tracking-quiet text-foreground/80">
                  {m.content}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
