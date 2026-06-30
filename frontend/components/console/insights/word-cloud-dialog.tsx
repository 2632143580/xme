'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import cloud from 'd3-cloud'
import type { ChatMessage } from '@/lib/console-types'
import { computeWordFrequency, type WordCount } from '@/lib/word-frequency'
import { EmptyState } from '../empty-state'
import {
  InsightOverlay,
  RangeTabs,
  filterByRange,
  type TimeRange,
} from './insight-overlay'

type PlacedWord = WordCount & {
  x: number
  y: number
  size: number
  rotate: number
}

// 冷色信号梯度：词频越高越接近主信号色
const PALETTE = [
  'oklch(0.66 0.09 234)',
  'oklch(0.6 0.06 222)',
  'oklch(0.56 0.045 210)',
  'oklch(0.6 0.03 246)',
  'oklch(0.66 0.034 66)', // 极少量暖灰呼吸点
]

export function WordCloudDialog({
  messages,
  onClose,
}: {
  messages: ChatMessage[]
  onClose: () => void
}) {
  const [range, setRange] = useState<TimeRange>('all')
  const [placed, setPlaced] = useState<PlacedWord[] | null>(null)
  const [computing, setComputing] = useState(true)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  const words = useMemo(() => {
    // 只统计自然语言对话，跳过 reminder 系统提示（如降级/未送达通知）
    const texts = filterByRange(messages, range)
      .filter((m) => m.role !== 'reminder')
      .map((m) => m.content)
    return computeWordFrequency(texts, 70)
  }, [messages, range])

  // d3-cloud 布局计算
  useEffect(() => {
    if (words.length === 0) {
      setPlaced([])
      setComputing(false)
      return
    }
    setComputing(true)
    const box = boxRef.current
    const width = box?.clientWidth ?? 560
    const height = 360
    const max = words[0].count
    const min = words[words.length - 1].count
    const scale = (c: number) => {
      if (max === min) return 30
      return 16 + ((c - min) / (max - min)) * 48 // 16–64px
    }

    let cancelled = false
    const layout = cloud<PlacedWord>()
      .size([width, height])
      .words(words.map((w) => ({ ...w, x: 0, y: 0, size: scale(w.count), rotate: 0 })))
      .padding(3)
      .rotate(() => 0)
      .font('Newsreader, Georgia, serif')
      .fontSize((d) => d.size)
      .on('end', (out) => {
        if (!cancelled) {
          setPlaced(out as PlacedWord[])
          setComputing(false)
        }
      })
    layout.start()
    return () => {
      cancelled = true
      layout.stop()
    }
  }, [words])

  // 绘制到 Canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !placed || placed.length === 0) return
    const box = boxRef.current
    const width = box?.clientWidth ?? 560
    const height = 360
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)
    ctx.translate(width / 2, height / 2)
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    const max = placed.reduce((m, w) => Math.max(m, w.count), 0)
    for (const w of placed) {
      const ratio = max > 0 ? w.count / max : 0
      const idx = Math.min(PALETTE.length - 1, Math.floor((1 - ratio) * PALETTE.length))
      ctx.save()
      ctx.translate(w.x, w.y)
      ctx.rotate((w.rotate * Math.PI) / 180)
      ctx.font = `300 ${w.size}px Newsreader, Georgia, serif`
      ctx.fillStyle = PALETTE[idx]
      ctx.globalAlpha = 0.55 + ratio * 0.4
      ctx.fillText(w.text, 0, 0)
      ctx.restore()
    }
  }, [placed])

  const total = words.reduce((s, w) => s + w.count, 0)

  return (
    <InsightOverlay
      title="词云"
      subtitle="从这段对话里浮现出来的词，频次越高，字越大。"
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between text-[12px] tracking-quiet text-faint">
          <span>{words.length > 0 ? `${words.length} 个词 · 共 ${total} 次` : '没有可统计的词'}</span>
          <span className="font-mono">本地计算 · 不上传</span>
        </div>
      }
    >
      <div className="mb-4 flex justify-center">
        <RangeTabs value={range} onChange={setRange} />
      </div>

      <div
        ref={boxRef}
        className="relative flex min-h-[360px] items-center justify-center overflow-hidden rounded-xl border border-border/40 bg-surface/30"
      >
        {computing && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="animate-pulse-slow font-display text-sm font-light italic tracking-quiet text-faint">
              正在拾词……
            </span>
          </div>
        )}
        {!computing && words.length === 0 && (
          <EmptyState
            variant="signal"
            title="这段时间没有词可拾"
            hint="换个时间范围，或先和它聊几句。"
          />
        )}
        <canvas ref={canvasRef} className={computing ? 'opacity-0' : 'animate-fade-in'} />
      </div>
    </InsightOverlay>
  )
}
