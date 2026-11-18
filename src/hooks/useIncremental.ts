import { useEffect, useRef, useState } from "react";

/**
 * Renders long lists in chunks: shows `step` items first and loads more
 * when the sentinel element scrolls near the viewport.
 */
export function useIncremental<T>(items: readonly T[], step = 60) {
  const [count, setCount] = useState(step);
  const sentinel = useRef<HTMLDivElement | null>(null);

  // Start over whenever the list changes (new search or filter).
  useEffect(() => {
    setCount(step);
  }, [items, step]);

  const hasMore = count < items.length;

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) setCount((c) => c + step);
      },
      { rootMargin: "600px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, count, step]);

  return { visible: items.slice(0, count), hasMore, sentinel };
}
