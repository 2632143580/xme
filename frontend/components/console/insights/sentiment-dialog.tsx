'use client'

import { useEffect, useRef, useState } from 'react'
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Filler,
} from 'chart.js'
import type { ChatMessage } from '@/lib/console-types'
import {
  SENTIMENT_MODEL,
  SENTIMENT_TEXT,
  toSentiment,
  type SentimentPoint,
} from '@/lib/sentiment'
import { formatTime } from '@/lib/format'
import { EmptyState } from '../empty-state'
import { InsightOverlay } from './insight-overlay'

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Filler,
)

type Phase = 'idle' | 'loading-model' | 'analyzing' | 'done' | 'error'

// 模型管线单例：只下载一次，后续复用（权重由浏览器 Cache 持久化）
let _pipe: unknown = null

export function SentimentDialog({
  messages,
  onClose,
}: {
  messages: ChatMessage[]
  onClose: () => void
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState(0)
  const [hint, setHint] = useState('准备模型……')
  const [points, setPoints] = useState<SentimentPoint[]>([])
  const [error, setError] = useState('')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  // 只分析用户与助手的自然语言，跳过提醒系统提示
  const targets = messages.filter((m) => m.role !== 'reminder' && m.content.trim())

  useEffect(() => {
    let cancelled = false

    async function run() {
      if (targets.length === 0) {
        setPhase('done')
        return
      }
      try {
        setPhase('loading-model')
        setHint('正在取回情绪模型……')
        const { pipeline, env } = await import('@huggingface/transformers')

        // Hugging Face 官方 CDN 国内不通，改用镜像站取回模型权重
        env.remoteHost = 'https://hf-mirror.com'
        env.remotePathTemplate = '{model}/resolve/{revision}/{file}'

        if (!_pipe) {
          _pipe = await pipeline('sentiment-analysis', SENTIMENT_MODEL, {
            device: 'webgpu',
            progress_callback: (p: { status?: string; progress?: number }) => {
              if (cancelled) return
              if (p.status === 'progress' && typeof p.progress === 'number') {
                setProgress(Math.round(p.progress))
              }
            },
          })
        }
        if (cancelled) return

        setPhase('analyzing')
        setHint('正在逐句体会……')
        const classify = _pipe as (t: string) => Promise<{ label: string; score: number }[]>
        const out: SentimentPoint[] = []
        for (let i = 0; i < targets.length; i++) {
          if (cancelled) return
          const m = targets[i]
          const res = await classify(m.content)
          const top = Array.isArray(res) ? res[0] : (res as { label: string; score: number })
          const { label, value } = toSentiment(top?.label ?? 'neutral')
          out.push({
            label,
            value,
            score: top?.score ?? 0,
            text: m.content,
            created_at: m.created_at,
          })
          setProgress(Math.round(((i + 1) / targets.length) * 100))
        }
        if (cancelled) return
        setPoints(out)
        setPhase('done')
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '分析失败')
        setPhase('error')
      }
    }

    run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 绘制折线图
  useEffect(() => {
    if (phase !== 'done' || points.length === 0) return
    const canvas = canvasRef.current
    if (!canvas) return
    chartRef.current?.destroy()

    const labels = points.map((_, i) => `#${i + 1}`)
    chartRef.current = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            data: points.map((p) => p.value),
            borderColor: 'oklch(0.66 0.09 234)',
            borderWidth: 1.5,
            tension: 0.35,
            fill: true,
            backgroundColor: (c) => {
              const { ctx, chartArea } = c.chart
              if (!chartArea) return 'transparent'
              const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
              g.addColorStop(0, 'oklch(0.66 0.09 234 / 0.22)')
              g.addColorStop(1, 'oklch(0.66 0.09 234 / 0)')
              return g
            },
            pointBackgroundColor: points.map((p) =>
              p.value > 0
                ? 'oklch(0.7 0.08 168)'
                : p.value < 0
                  ? 'oklch(0.66 0.034 66)'
                  : 'oklch(0.6 0.03 246)',
            ),
            pointBorderColor: 'transparent',
            pointRadius: 3,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        scales: {
          y: {
            min: -1.2,
            max: 1.2,
            ticks: {
              stepSize: 1,
              color: 'oklch(0.55 0.012 246)',
              font: { size: 11 },
              callback: (v) =>
                v === 1 ? '积极' : v === 0 ? '平静' : v === -1 ? '低落' : '',
            },
            grid: { color: 'oklch(0.4 0.015 248 / 0.14)' },
          },
          x: {
            ticks: { color: 'oklch(0.45 0.012 246)', font: { size: 10 }, maxRotation: 0 },
            grid: { display: false },
          },
        },
        plugins: {
          tooltip: {
            backgroundColor: 'oklch(0.218 0.015 251)',
            borderColor: 'oklch(0.4 0.015 248 / 0.4)',
            borderWidth: 1,
            titleColor: 'oklch(0.84 0.012 236)',
            bodyColor: 'oklch(0.7 0.013 240)',
            padding: 10,
            displayColors: false,
            callbacks: {
              title: (items) => {
                const p = points[items[0].dataIndex]
                const t = formatTime(p.created_at)
                return `${SENTIMENT_TEXT[p.label]} · 置信 ${(p.score * 100).toFixed(0)}%${t ? ` · ${t}` : ''}`
              },
              label: (item) => {
                const p = points[item.dataIndex]
                const text = p.text.length > 40 ? `${p.text.slice(0, 40)}…` : p.text
                return text
              },
            },
          },
        },
      },
    })

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [phase, points])

  const busy = phase === 'loading-model' || phase === 'analyzing'

  return (
    <InsightOverlay
      title="情绪趋势"
      subtitle="逐句体会这段对话的起伏，全部在你的浏览器里完成。"
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between text-[12px] tracking-quiet text-faint">
          <span>
            {phase === 'done' && points.length > 0
              ? `${points.length} 条 · 已分析`
              : phase === 'error'
                ? '分析中断'
                : busy
                  ? hint
                  : '本地推理'}
          </span>
          <span className="font-mono">WebGPU · 不上传</span>
        </div>
      }
    >
      <div className="relative flex min-h-[340px] flex-col">
        {busy && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10">
            <span className="animate-pulse-slow font-display text-sm font-light italic tracking-quiet text-muted-foreground">
              {hint}
            </span>
            <div className="h-1 w-56 overflow-hidden rounded-full bg-surface-2/60">
              <div
                className="h-full rounded-full bg-signal/70 transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="font-mono text-[11px] text-faint">{progress}%</span>
          </div>
        )}

        {phase === 'error' && (
          <EmptyState
            variant="signal"
            title="没能读出情绪"
            hint={error || '模型加载受阻，稍后再试。'}
          />
        )}

        {phase === 'done' && points.length === 0 && (
          <EmptyState
            variant="signal"
            title="还没有可分析的话"
            hint="先和它聊几句，再回来看情绪的起伏。"
          />
        )}

        {phase === 'done' && points.length > 0 && (
          <div className="animate-fade-in relative h-[340px] w-full">
            <canvas ref={canvasRef} />
          </div>
        )}
      </div>
    </InsightOverlay>
  )
}
