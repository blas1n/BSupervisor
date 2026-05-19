import { useEffect, useRef, useState } from "react";

/**
 * Returns a `ref` plus a `ready` flag that flips `true` once the
 * referenced element has a non-zero size.
 *
 * Use it to gate the mount of a recharts `<ResponsiveContainer>`:
 * recharts logs a `width(-1) and height(-1)` console warning whenever
 * its *measured* container is 0 on the first mount frame — which happens
 * before the browser has laid the box out. CSS sizing (`minHeight`, a
 * fixed-height parent) does not prevent it. Mounting the chart only
 * after `ready` means recharts' first measure is always valid.
 */
export function useMeasuredRef<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => {
      const { width, height } = el.getBoundingClientRect();
      if (width > 0 && height > 0) setReady(true);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, ready };
}
