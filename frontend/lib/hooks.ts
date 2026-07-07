"use client";

/**
 * Shared client-side hooks & async helpers.
 *
 * - `useAsync` covers the repeated "fetch on mount, keep data/error/loading,
 *   ignore resolutions after unmount" pattern used across pages.
 * - `pollUntil` + `useUnmountSignal` cover the generation-job polling loops
 *   (new-request flow and DocumentViewer refinements) with proper
 *   cancellation when the component unmounts.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Interval between generation-job polls (SPEC: poll every 2s). */
export const JOB_POLL_INTERVAL_MS = 2000;

interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
}

/**
 * Runs `fn` on mount (and whenever `deps` change), tracking data/error/loading.
 * Resolutions that land after unmount (or after deps changed) are ignored, so
 * no setState happens on an unmounted component. `reload()` re-runs `fn`.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);

  // Always call the latest `fn` without forcing callers to memoize it.
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, error: null, loading: true });
    fnRef.current().then(
      (data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      },
      (error: unknown) => {
        if (!cancelled) setState({ data: null, error, loading: false });
      },
    );
    return () => {
      cancelled = true;
    };
    // `deps` is intentionally spread: it plays the role of a dependency list.
  }, [...deps, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(() => setTick((n) => n + 1), []);

  return { ...state, reload };
}

function abortError(): Error {
  return new DOMException("The operation was aborted.", "AbortError");
}

/** True when `err` is the AbortError raised by `sleep`/`pollUntil` on cancel. */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/** Cancellable sleep: rejects with an AbortError when `signal` aborts. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(id);
      reject(abortError());
    };
    const id = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Polls `fn` every `intervalMs` (sleeping first, matching the previous
 * behavior of the for(;;) loops) until `done(result)` is true, then resolves
 * with that result. Rejects with an AbortError as soon as `signal` aborts,
 * so an unmounted component stops hitting the API.
 */
export async function pollUntil<T>(opts: {
  fn: () => Promise<T>;
  done: (result: T) => boolean;
  intervalMs?: number;
  signal?: AbortSignal;
}): Promise<T> {
  const { fn, done, intervalMs = JOB_POLL_INTERVAL_MS, signal } = opts;
  for (;;) {
    await sleep(intervalMs, signal);
    const result = await fn();
    if (signal?.aborted) throw abortError();
    if (done(result)) return result;
  }
}

/**
 * Returns a getter for an AbortSignal tied to the component lifecycle: the
 * signal aborts when the component unmounts. A fresh controller is created
 * per mount (StrictMode-safe), so async event handlers can do:
 *
 *   const getSignal = useUnmountSignal();
 *   async function handler() {
 *     const signal = getSignal();
 *     await pollUntil({ ..., signal });
 *     if (signal.aborted) return;
 *     // safe to setState here
 *   }
 */
export function useUnmountSignal(): () => AbortSignal {
  const ref = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    ref.current = controller;
    return () => {
      controller.abort();
      if (ref.current === controller) ref.current = null;
    };
  }, []);

  return useCallback(() => {
    if (!ref.current || ref.current.signal.aborted) {
      ref.current = new AbortController();
    }
    return ref.current.signal;
  }, []);
}
