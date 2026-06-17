/**
 * Lol-AI-lo logo — "bracket frame" mark (concept 4a): two opposite legal-style
 * corner brackets framing a brass centre dot, plus the Fraunces wordmark.
 * Theme-aware (brackets use the brand colour, which lifts to sage in dark).
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
      {/* top-left bracket */}
      <path
        d="M7 7h7M7 7v7"
        className="stroke-brand-700"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      {/* bottom-right bracket */}
      <path
        d="M25 25h-7M25 25v-7"
        className="stroke-brand-700"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      {/* brass centre dot */}
      <circle cx="16" cy="16" r="2.2" className="fill-accent-500" />
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
      <span className="font-display text-xl font-semibold tracking-tight text-ink-900">
        Lol<span className="text-brand-600">·AI·</span>lo
      </span>
    </span>
  );
}
