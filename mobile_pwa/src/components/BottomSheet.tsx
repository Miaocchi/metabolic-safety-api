import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useHaptics, usePlatform } from "../hooks/usePlatform";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  children: ReactNode;
  showGrabber?: boolean;
  dismissible?: boolean;
}

export function BottomSheet({ open, onClose, title, subtitle, children, showGrabber = true, dismissible = true }: BottomSheetProps) {
  const [visible, setVisible] = useState(false);
  const [animating, setAnimating] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const grabberRef = useRef<HTMLDivElement>(null);
  const startY = useRef(0);
  const currentY = useRef(0);
  const pulling = useRef(false);
  const haptics = useHaptics();
  const platform = usePlatform();

  useEffect(() => {
    if (open) {
      setVisible(true);
      requestAnimationFrame(() => setAnimating(true));
    } else {
      setAnimating(false);
      const timer = setTimeout(() => setVisible(false), 350);
      return () => clearTimeout(timer);
    }
  }, [open]);

  const handleClose = useCallback(() => {
    if (!dismissible) return;
    haptics("light");
    onClose();
  }, [dismissible, haptics, onClose]);

  // 只在 grabber 区域绑定下拉关闭手势，避免干扰 sheet 内部滚动
  useEffect(() => {
    const grabber = grabberRef.current;
    if (!grabber || !dismissible) return;

    function touchStart(e: TouchEvent) {
      startY.current = e.touches[0].clientY;
      currentY.current = 0;
      pulling.current = false;
    }

    function touchMove(e: TouchEvent) {
      const delta = e.touches[0].clientY - startY.current;
      if (delta > 0) {
        if (!pulling.current && delta > 10) {
          pulling.current = true;
        }
        if (pulling.current) {
          e.preventDefault();
          currentY.current = delta;
          if (sheetRef.current) {
            sheetRef.current.style.transform = `translateY(${delta}px)`;
            sheetRef.current.style.transition = "none";
          }
        }
      }
    }

    function touchEnd() {
      if (sheetRef.current) {
        sheetRef.current.style.transition = "";
        sheetRef.current.style.transform = "";
      }
      if (pulling.current && currentY.current > 80) {
        handleClose();
      }
      pulling.current = false;
      currentY.current = 0;
    }

    grabber.addEventListener("touchstart", touchStart, { passive: true });
    grabber.addEventListener("touchmove", touchMove, { passive: false });
    grabber.addEventListener("touchend", touchEnd, { passive: true });
    grabber.addEventListener("touchcancel", touchEnd, { passive: true });

    return () => {
      grabber.removeEventListener("touchstart", touchStart);
      grabber.removeEventListener("touchmove", touchMove);
      grabber.removeEventListener("touchend", touchEnd);
      grabber.removeEventListener("touchcancel", touchEnd);
    };
  }, [dismissible, handleClose]);

  if (!visible) return null;

  return (
    <div
      className={`sheet-backdrop ${animating ? "active" : ""}`}
      onClick={handleClose}
      style={{
        opacity: animating ? 1 : 0,
        transition: "opacity 0.28s cubic-bezier(0.32, 0.72, 0, 1)",
      }}
    >
      <aside
        ref={sheetRef}
        className={`bottom-sheet ${animating ? "active" : ""}`}
        onClick={(e) => e.stopPropagation()}
        style={{
          transform: animating ? "translateY(0)" : "translateY(100%)",
          transition: "transform 0.35s cubic-bezier(0.32, 0.72, 0, 1)",
          paddingBottom: platform.isMobile ? `calc(18px + max(env(safe-area-inset-bottom), ${platform.safeAreaBottom}px))` : "18px",
        }}
      >
        {showGrabber && (
          <div ref={grabberRef} className="sheet-grabber" style={{ cursor: dismissible ? "grab" : "default" }} />
        )}
        {(title || subtitle) && (
          <header className="sheet-header">
            <div>
              {subtitle && <span>{subtitle}</span>}
              {title && <h2>{title}</h2>}
            </div>
            <button type="button" onClick={handleClose} aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </header>
        )}
        {children}
      </aside>
    </div>
  );
}
