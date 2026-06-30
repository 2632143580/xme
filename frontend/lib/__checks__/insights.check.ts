// 纯逻辑自检：运行 `npx tsx lib/__checks__/insights.check.ts`
import { strict as assert } from 'node:assert'
import { toSentiment } from '../sentiment'
import { computeWordFrequency } from '../word-frequency'

// 情绪映射：星级 / 英文标签 → 三态
assert.deepEqual(toSentiment('1 star'), { label: 'negative', value: -1 })
assert.deepEqual(toSentiment('2 stars'), { label: 'negative', value: -1 })
assert.deepEqual(toSentiment('3 stars'), { label: 'neutral', value: 0 })
assert.deepEqual(toSentiment('5 stars'), { label: 'positive', value: 1 })
assert.deepEqual(toSentiment('POSITIVE'), { label: 'positive', value: 1 })
assert.deepEqual(toSentiment('negative'), { label: 'negative', value: -1 })

// 词频：停用词被过滤，重复词被合并计数
const freq = computeWordFrequency([
  '今天天气很好我很开心',
  '今天我也很开心因为天气好',
])
const map = new Map(freq.map((w) => [w.text, w.count]))
assert.ok(!map.has('我'), '“我”应被停用词过滤')
assert.ok(!map.has('的'), '“的”应被停用词过滤')
assert.ok((map.get('开心') ?? 0) >= 2, '“开心”应至少出现两次')
assert.ok(freq.every((w, i) => i === 0 || freq[i - 1].count >= w.count), '应按频次降序')

console.log('[checks] insights 纯逻辑全部通过 ·', freq.length, '个词')
