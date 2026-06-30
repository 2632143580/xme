// 情绪标签映射（纯函数）。模型输出多语言星级，归一到 三态 + 数值。
export type SentimentLabel = 'positive' | 'neutral' | 'negative'

export interface SentimentPoint {
  label: SentimentLabel
  value: -1 | 0 | 1
  score: number // 模型置信度 0–1
  text: string
  created_at: string
}

// ponytail: 复用社区现成的多语言情绪模型（nlptown 1–5 星），无需自训。
// 中文支持良好，transformers.js 自动从 CDN 拉取 ONNX 权重并走浏览器 Cache 缓存。
export const SENTIMENT_MODEL = 'Xenova/bert-base-multilingual-uncased-sentiment'

/** 把模型 label（如 "4 stars" / "POSITIVE" / "negative"）映射为三态 */
export function toSentiment(rawLabel: string): { label: SentimentLabel; value: -1 | 0 | 1 } {
  const l = rawLabel.toLowerCase()
  const starMatch = l.match(/([1-5])\s*star/)
  if (starMatch) {
    const star = Number(starMatch[1])
    if (star <= 2) return { label: 'negative', value: -1 }
    if (star === 3) return { label: 'neutral', value: 0 }
    return { label: 'positive', value: 1 }
  }
  if (l.includes('pos')) return { label: 'positive', value: 1 }
  if (l.includes('neg')) return { label: 'negative', value: -1 }
  return { label: 'neutral', value: 0 }
}

export const SENTIMENT_TEXT: Record<SentimentLabel, string> = {
  positive: '积极',
  neutral: '平静',
  negative: '低落',
}

/**
 * WebGPU 是否真正可用：不仅要有 navigator.gpu，还要能拿到 GPU 适配器。
 * 仅判断 API 存在会误判（headless / 无独显环境 API 在但 requestAdapter 失败），
 * 实际请求一次 adapter 才是可靠的降级依据。
 */
export async function hasWebGPU(): Promise<boolean> {
  if (typeof navigator === 'undefined' || !('gpu' in navigator) || !navigator.gpu) {
    return false
  }
  try {
    const adapter = await navigator.gpu.requestAdapter()
    return !!adapter
  } catch {
    return false
  }
}
