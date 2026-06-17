/**
 * Lol-AI-lo logo — a document mark with a gold "AI" accent dot, plus the
 * Fraunces wordmark. Decorative; aria-hidden where a text label exists.
 */

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" className="fill-ink-900" />
      {/* stylised document */}
      <path
        d="M11 8.5h6.4L22 13v10.5a1 1 0 0 1-1 1H11a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1Z"
        className="fill-canvas"
      />
      <path d="M17.2 8.6V13H21" className="stroke-ink-300" strokeWidth="1.1" />
      <path
        d="M12.6 16h6.8M12.6 18.6h6.8M12.6 21.2h4.2"
        className="stroke-ink-400"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
      {/* AI accent dot */}
      <circle cx="22.5" cy="21.5" r="3.2" className="fill-brand-500" />
    </svg>
  );
}

export function Wordmark({
  className,
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <LogoMark className={markClassName ?? "h-7 w-7"} />
      <span className="text-xl font-semibold tracking-tight text-ink-900">
        Lol<span className="text-brand-500">·AI·</span>lo
      </span>
    </span>
  );
}
