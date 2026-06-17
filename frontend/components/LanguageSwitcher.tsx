"use client";

import { useI18n } from "@/components/I18nProvider";
import { LOCALES, LOCALE_LABELS, type Locale } from "@/lib/i18n";

export default function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();

  return (
    <select
      aria-label={t("common.language")}
      value={locale}
      onChange={(e) => setLocale(e.target.value as Locale)}
      className="rounded-md border border-ink-300 bg-surface px-2 py-1 text-xs text-ink-600 focus:border-brand-500 focus:outline-none"
    >
      {LOCALES.map((l) => (
        <option key={l} value={l}>
          {LOCALE_LABELS[l]}
        </option>
      ))}
    </select>
  );
}
