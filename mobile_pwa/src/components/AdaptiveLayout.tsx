import { type ReactNode } from "react";
import { usePlatform } from "../hooks/usePlatform";

interface AdaptiveLayoutProps {
  children: ReactNode;
  sidebar?: ReactNode;
  topChrome?: ReactNode;
  navigationBar?: ReactNode;
  tabBar?: ReactNode;
  pullToRefresh?: boolean;
  onRefresh?: () => Promise<void> | void;
}

export function AdaptiveLayout({
  children,
  sidebar,
  topChrome,
  navigationBar,
  tabBar,
}: AdaptiveLayoutProps) {
  const platform = usePlatform();

  if (platform.isDesktop) {
    return (
      <div className="app desktop">
        {sidebar}
        <div className="desktop-main">
          {topChrome}
          {navigationBar}
          <main className="screen">
            {children}
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className={`app mobile ${platform.os}`}>
      {navigationBar}
      <main className="screen">
        {topChrome}
        {children}
      </main>
      {tabBar}
    </div>
  );
}
