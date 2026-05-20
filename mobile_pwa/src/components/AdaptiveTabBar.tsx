import { type ReactNode, useCallback } from "react";
import { useHaptics, usePlatform } from "../hooks/usePlatform";

export interface TabItem {
  key: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: number;
}

interface AdaptiveTabBarProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (key: string) => void;
  className?: string;
  hidden?: boolean;
}

export function AdaptiveTabBar({ tabs, activeTab, onChange, className, hidden }: AdaptiveTabBarProps) {
  const platform = usePlatform();
  const haptics = useHaptics();

  const handleClick = useCallback(
    (key: string) => {
      if (key === activeTab) return;
      haptics("light");
      onChange(key);
    },
    [activeTab, haptics, onChange],
  );

  if (platform.isDesktop) {
    return (
      <nav className={`sidebar ${className || ""}`} aria-label="主导航">
        <div className="sidebar-header">
          <span className="sidebar-brand">代谢安全</span>
        </div>
        <div className="sidebar-tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                className={isActive ? "active" : ""}
                type="button"
                onClick={() => handleClick(tab.key)}
                aria-current={isActive ? "page" : undefined}
              >
                <Icon size={20} />
                <span>{tab.label}</span>
                {tab.badge ? <em className="tab-badge">{tab.badge}</em> : null}
              </button>
            );
          })}
        </div>
      </nav>
    );
  }

  return (
    <nav
      className={`tabbar ${hidden ? "hidden" : ""} ${className || ""}`}
      aria-label="主导航"
      style={{
        bottom: `max(12px, env(safe-area-inset-bottom), ${platform.safeAreaBottom}px)`,
      }}
    >
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            className={isActive ? "active" : ""}
            type="button"
            onClick={() => handleClick(tab.key)}
            aria-current={isActive ? "page" : undefined}
          >
            <Icon size={platform.device === "tablet" ? 24 : 21} />
            <span>{tab.label}</span>
            {tab.badge ? <em className="tab-badge">{tab.badge}</em> : null}
          </button>
        );
      })}
    </nav>
  );
}
