"use client";

/**
 * Small shared UI primitives — Tailwind only, no component library deps.
 */

import {
  forwardRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/* ----------------------------- Button ----------------------------- */

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  // Monochrome primary: near-black in light, near-white in dark (ink flips).
  primary:
    "bg-ink-900 text-canvas hover:bg-ink-800 focus-visible:ring-brand-500 disabled:bg-ink-200 disabled:text-ink-400",
  secondary:
    "bg-surface text-ink-700 border border-ink-200 hover:bg-ink-100 hover:border-ink-300 focus-visible:ring-brand-500 disabled:text-ink-300",
  danger:
    "bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500 disabled:bg-ink-200",
  ghost:
    "bg-transparent text-ink-600 hover:bg-ink-100 focus-visible:ring-brand-500 disabled:text-ink-300",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button({ variant = "primary", className, ...props }, ref) {
    return (
      <button
        ref={ref}
        className={cx(
          "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100",
          BUTTON_VARIANTS[variant],
          className,
        )}
        {...props}
      />
    );
  },
);

/* ------------------------------ Card ------------------------------ */

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "rounded-xl border border-ink-200 bg-surface p-6 shadow-card",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2 className={cx("text-base font-semibold text-ink-900", className)}>
      {children}
    </h2>
  );
}

/* ------------------------------ Badge ----------------------------- */

type BadgeTone =
  | "slate"
  | "sky"
  | "indigo"
  | "amber"
  | "violet"
  | "emerald"
  | "green"
  | "red";

const BADGE_TONES: Record<BadgeTone, string> = {
  slate: "bg-ink-100 text-ink-700 ring-ink-200",
  sky: "bg-sky-100 text-sky-800 ring-sky-200",
  indigo: "bg-indigo-100 text-indigo-800 ring-indigo-200",
  amber: "bg-amber-100 text-amber-800 ring-amber-200",
  violet: "bg-violet-100 text-violet-800 ring-violet-200",
  emerald: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  green: "bg-green-100 text-green-800 ring-green-200",
  red: "bg-red-100 text-red-800 ring-red-200",
};

export function Badge({
  tone = "slate",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export type { BadgeTone };

/* ------------------------------ Inputs ---------------------------- */

const FIELD_BASE =
  "w-full rounded-lg border border-ink-200 bg-surface px-3 py-2 text-sm text-ink-900 placeholder:text-ink-300 transition-colors focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 disabled:bg-ink-100 disabled:text-ink-300";

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cx(FIELD_BASE, className)} {...props} />;
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea ref={ref} className={cx(FIELD_BASE, className)} {...props} />
  );
});

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ className, ...props }, ref) {
  return <select ref={ref} className={cx(FIELD_BASE, className)} {...props} />;
});

export function Label({
  children,
  htmlFor,
  className,
}: {
  children: ReactNode;
  htmlFor?: string;
  className?: string;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className={cx("mb-1.5 block text-sm font-medium text-ink-700", className)}
    >
      {children}
    </label>
  );
}

/* --------------------------- Usage bar ---------------------------- */

/**
 * Consumption progress bar (billing, improvement #7).
 * Tone by percentage of the allowance: green <80%, amber 80–100%, red >100%.
 */
export function UsageBar({
  pct,
  className,
}: {
  /** 0–100+ (values past 100 render a full red bar). */
  pct: number;
  className?: string;
}) {
  const tone =
    pct > 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cx(
        "h-2 w-full overflow-hidden rounded-full bg-ink-200",
        className,
      )}
    >
      <div
        className={cx("h-full rounded-full transition-all", tone)}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

/* ----------------------------- Spinner ---------------------------- */

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx("h-5 w-5 animate-spin text-brand-700", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

/* ------------------------------ Banner ---------------------------- */

type BannerTone = "info" | "warning" | "danger" | "success";

const BANNER_TONES: Record<BannerTone, string> = {
  info: "border-sky-200 bg-sky-50 text-sky-900",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  danger: "border-red-300 bg-red-50 text-red-900",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
};

export function Banner({
  tone = "info",
  children,
  className,
}: {
  tone?: BannerTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "rounded-md border px-4 py-3 text-sm leading-relaxed",
        BANNER_TONES[tone],
        className,
      )}
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

/* --------------------------- Page header -------------------------- */

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-[1.7rem] font-semibold leading-tight tracking-tight text-ink-900">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1.5 max-w-2xl text-sm text-ink-400">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* ----------------------------- Toggle ----------------------------- */

export function Toggle({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  id?: string;
}) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
        checked ? "bg-brand-600" : "bg-ink-300",
      )}
    >
      <span
        className={cx(
          "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  );
}
