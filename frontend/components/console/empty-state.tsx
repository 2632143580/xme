// 空状态：低沉引导语 + 抽象线条图形，营造“安静在场”的叙事感。
export function EmptyState({
  title,
  hint,
  variant = 'signal',
}: {
  title: string
  hint?: string
  variant?: 'signal' | 'wave' | 'orbit'
}) {
  return (
    <div className="animate-fade-in flex flex-col items-center justify-center gap-5 px-6 py-14 text-center">
      <AbstractMark variant={variant} />
      <div className="space-y-1.5">
        <p className="font-display text-base font-light italic tracking-quiet text-foreground/70">
          {title}
        </p>
        {hint && (
          <p className="text-xs leading-relaxed tracking-quiet text-faint">{hint}</p>
        )}
      </div>
    </div>
  )
}

function AbstractMark({ variant }: { variant: 'signal' | 'wave' | 'orbit' }) {
  const stroke = 'oklch(0.55 0.04 244 / 0.5)'
  const faint = 'oklch(0.5 0.03 246 / 0.28)'
  return (
    <svg
      width="72"
      height="72"
      viewBox="0 0 72 72"
      fill="none"
      aria-hidden
      className="animate-pulse-slow"
    >
      {variant === 'signal' && (
        <>
          <circle cx="36" cy="36" r="3" fill={stroke} />
          <circle cx="36" cy="36" r="12" stroke={faint} strokeWidth="0.75" />
          <circle cx="36" cy="36" r="22" stroke={faint} strokeWidth="0.75" />
          <circle cx="36" cy="36" r="32" stroke={faint} strokeWidth="0.5" />
        </>
      )}
      {variant === 'wave' && (
        <path
          d="M4 36 Q14 22 24 36 T44 36 T64 36"
          stroke={stroke}
          strokeWidth="0.9"
          strokeLinecap="round"
        />
      )}
      {variant === 'orbit' && (
        <>
          <circle cx="36" cy="36" r="2.5" fill={stroke} />
          <ellipse cx="36" cy="36" rx="30" ry="12" stroke={faint} strokeWidth="0.75" />
          <ellipse
            cx="36"
            cy="36"
            rx="12"
            ry="30"
            stroke={faint}
            strokeWidth="0.5"
            transform="rotate(30 36 36)"
          />
        </>
      )}
    </svg>
  )
}
