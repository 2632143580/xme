// 签名元素：缓慢呼吸的微弱光晕。
// 光从中心向四角隐没，像深海或夜空尽头的信号。固定铺底，不参与交互。
export function AmbientGlow() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* 四角隐没的暗场 */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(120% 90% at 50% 38%, oklch(0.21 0.02 250) 0%, oklch(0.17 0.014 251) 42%, oklch(0.13 0.012 252) 100%)',
        }}
      />
      {/* 中心缓慢呼吸的冷色信号 */}
      <div
        className="animate-breathe absolute left-1/2 top-[34%] h-[60vmax] w-[60vmax] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
        style={{
          background:
            'radial-gradient(circle, oklch(0.55 0.09 236 / 0.16) 0%, oklch(0.5 0.07 240 / 0.06) 40%, transparent 70%)',
        }}
      />
      {/* 极弱暖灰呼吸点，作为微弱温度 */}
      <div
        className="animate-breathe absolute left-[62%] top-[58%] h-[26vmax] w-[26vmax] rounded-full blur-3xl"
        style={{
          background:
            'radial-gradient(circle, oklch(0.6 0.04 66 / 0.07) 0%, transparent 68%)',
          animationDelay: '4s',
        }}
      />
    </div>
  )
}
