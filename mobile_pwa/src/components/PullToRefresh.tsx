import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

interface PullToRefreshProps {
  onRefresh: () => Promise<void> | void;
  children: ReactNode;
  threshold?: number;
  maxPull?: number;
  disabled?: boolean;
  onScrollDirection?: (direction: "up" | "down") => void;
}

export function PullToRefresh({ onRefresh, children, threshold = 80, maxPull = 120, disabled, onScrollDirection }: PullToRefreshProps) {
  const [pullY, setPullY] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const lastTouchY = useRef<number | null>(null);
  const lastScrollTop = useRef(0);
  const pulling = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const canPull = useCallback(() => {
    const el = containerRef.current;
    if (!el) return false;
    return el.scrollTop <= 0;
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || disabled) return;

    function touchStart(e: TouchEvent) {
      if (refreshing) return;
      if (!canPull()) return;
      startY.current = e.touches[0].clientY;
      lastTouchY.current = e.touches[0].clientY;
      pulling.current = false;
    }

    function touchMove(e: TouchEvent) {
      if (startY.current === null || refreshing) return;

      const currentY = e.touches[0].clientY;
      const delta = currentY - startY.current;
      const step = lastTouchY.current === null ? 0 : currentY - lastTouchY.current;
      if (Math.abs(step) > 8) onScrollDirection?.(step < 0 ? "up" : "down");
      lastTouchY.current = currentY;

      // 还没进入 pulling 模式时，允许浏览器正常滚动
      if (!pulling.current) {
        if (delta > 10 && canPull()) {
          pulling.current = true;
        } else if (delta < -5) {
          // 向上滑动，取消跟踪
          startY.current = null;
          return;
        }
        // 小幅度移动时不拦截，让浏览器正常处理滚动
        return;
      }

      // 已进入 pulling 模式，接管滚动
      e.preventDefault();
      const damped = Math.min(delta * 0.5, maxPull);
      setPullY(damped);
    }

    function touchEnd() {
      if (startY.current === null) return;
      startY.current = null;
      lastTouchY.current = null;
      const wasPulling = pulling.current;
      pulling.current = false;

      if (!wasPulling) {
        setPullY(0);
        return;
      }

      if (pullY >= threshold && !refreshing) {
        setRefreshing(true);
        setPullY(threshold * 0.6);
        Promise.resolve(onRefresh()).finally(() => {
          setRefreshing(false);
          setPullY(0);
        });
      } else {
        setPullY(0);
      }
    }

    function scroll() {
      const current = containerRef.current?.scrollTop ?? 0;
      const delta = current - lastScrollTop.current;
      if (Math.abs(delta) > 10) onScrollDirection?.(delta > 0 ? "up" : "down");
      lastScrollTop.current = current;
    }

    el.addEventListener("touchstart", touchStart, { passive: true });
    el.addEventListener("touchmove", touchMove, { passive: false });
    el.addEventListener("touchend", touchEnd, { passive: true });
    el.addEventListener("touchcancel", touchEnd, { passive: true });
    el.addEventListener("scroll", scroll, { passive: true });

    return () => {
      el.removeEventListener("touchstart", touchStart);
      el.removeEventListener("touchmove", touchMove);
      el.removeEventListener("touchend", touchEnd);
      el.removeEventListener("touchcancel", touchEnd);
      el.removeEventListener("scroll", scroll);
    };
  }, [canPull, disabled, maxPull, onRefresh, onScrollDirection, pullY, refreshing, threshold]);

  return (
    <div
      ref={containerRef}
      className="ptr-container"
      style={{
        overflow: "auto",
        overscrollBehaviorY: "contain",
        WebkitOverflowScrolling: "touch",
        touchAction: "pan-y",
        flex: 1,
        position: "relative",
      }}
    >
      <div
        style={{
          height: pullY,
          overflow: "hidden",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          paddingBottom: 12,
          transition: startY.current === null ? "height 0.28s cubic-bezier(0.32, 0.72, 0, 1)" : "none",
        }}
      >
        {refreshing ? (
          <span className="ptr-spinner" />
        ) : (
          <span
            style={{
              fontSize: 13,
              color: "var(--muted)",
              fontWeight: 600,
              opacity: Math.min(pullY / threshold, 1),
              transition: "opacity 0.15s ease",
            }}
          >
            {pullY >= threshold ? "松开刷新" : "下拉刷新"}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
