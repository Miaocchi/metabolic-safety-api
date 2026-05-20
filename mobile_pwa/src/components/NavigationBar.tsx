import { type ReactNode } from "react";
import { usePlatform } from "../hooks/usePlatform";

interface NavigationBarProps {
  title: string;
  subtitle?: string;
  left?: ReactNode;
  right?: ReactNode;
  transparent?: boolean;
}

export function NavigationBar({ title, subtitle, left, right, transparent }: NavigationBarProps) {
  const platform = usePlatform();
  const isApple = platform.family === "apple";

  return (
    <header
      className={`navigation-bar ${transparent ? "transparent" : ""}`}
      style={{
        paddingTop: platform.isMobile ? `max(env(safe-area-inset-top), ${platform.safeAreaTop}px)` : undefined,
      }}
    >
      <div className="navigation-bar-content">
        <div className="navigation-bar-left">{left}</div>
        <div className="navigation-bar-center">
          {isApple && subtitle ? (
            <>
              <span className="navigation-bar-subtitle">{subtitle}</span>
              <h1 className="navigation-bar-title">{title}</h1>
            </>
          ) : (
            <h1 className="navigation-bar-title">{title}</h1>
          )}
        </div>
        <div className="navigation-bar-right">{right}</div>
      </div>
    </header>
  );
}
