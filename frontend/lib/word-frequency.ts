// 中文分词 + 停用词过滤 + 词频统计（纯前端，输入为内存消息文本）
import { Segment, useDefault } from 'segmentit'

// 高频虚词 / 停用词：用户指定的核心集合 + 常见标点与英文虚词
const STOPWORDS = new Set([
  '的', '了', '是', '我', '你', '他', '她', '它', '在', '有', '不', '也', '就',
  '这', '那', '和', '与', '吧', '呢', '啊', '吗', '哦', '嗯', '都', '要', '会',
  '着', '过', '到', '说', '让', '把', '被', '给', '为', '又', '还', '没', '很',
  '太', '再', '已经', '一个', '一下', '什么', '怎么', '这个', '那个', '我们',
  '你们', '他们', '自己', '可以', '没有', '这样', '那样', '因为', '所以',
  '但是', '如果', '一些', '现在', '知道', '觉得',
  'the', 'a', 'an', 'is', 'are', 'to', 'of', 'and', 'in', 'it', 'i', 'you',
])

export interface WordCount {
  text: string
  count: number
}

let _segment: Segment | null = null
function getSegment(): Segment {
  if (!_segment) _segment = useDefault(new Segment())
  return _segment
}

// 是否值得保留：过滤纯标点、单字虚词、空白、纯数字
function isMeaningful(word: string): boolean {
  const w = word.trim()
  if (!w) return false
  if (STOPWORDS.has(w.toLowerCase())) return false
  if (/^[\s\p{P}\p{S}]+$/u.test(w)) return false // 纯标点/符号
  if (/^\d+$/.test(w)) return false // 纯数字
  // 单个非中文字符（如孤立字母）跳过；单个中文字保留交由停用词把关
  if (w.length === 1 && !/[\u4e00-\u9fa5]/.test(w)) return false
  return true
}

/** 统计一组文本的词频，按频次降序返回 */
export function computeWordFrequency(texts: string[], topN = 80): WordCount[] {
  const segment = getSegment()
  const freq = new Map<string, number>()

  for (const text of texts) {
    if (!text) continue
    const words = segment.doSegment(text, { simple: true }) as string[]
    for (const raw of words) {
      const word = raw.trim()
      if (!isMeaningful(word)) continue
      freq.set(word, (freq.get(word) ?? 0) + 1)
    }
  }

  return [...freq.entries()]
    .map(([text, count]) => ({ text, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, topN)
}
