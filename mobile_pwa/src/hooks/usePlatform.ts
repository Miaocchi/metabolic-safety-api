import { useCallback, useEffect, useState } from "react";

export type PlatformOS = "ios" | "android" | "windows" | "macos" | "linux" | "unknown";
export type PlatformFamily = "apple" | "android" | "windows" | "other";
export type DeviceType = "mobile" | "tablet" | "desktop";

export interface PlatformInfo {
  os: PlatformOS;
  family: PlatformFamily;
  device: DeviceType;
  standalone: boolean;
  touch: boolean;
  reducedMotion: boolean;
  highContrast: boolean;
  darkMode: boolean;
  safeAreaTop: number;
  safeAreaBottom: number;
  screenWidth: number;
  screenHeight: number;
  isPWA: boolean;
  isMobile: boolean;
  isDesktop: boolean;
}

function detectOS(): PlatformOS {
  const ua = navigator.userAgent;
  if (/iPad|iPhone|iPod/.test(ua)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Mac/.test(ua) && !/iPhone|iPad|iPod/.test(ua)) {
    if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return "ios";
    return "macos";
  }
  if (/Windows/.test(ua)) return "windows";
  if (/Linux/.test(ua)) return "linux";
  return "unknown";
}

function detectDevice(os: PlatformOS, width: number, height: number): DeviceType {
  const shortSide = Math.min(width, height);
  const longSide = Math.max(width, height);
  if (os === "ios" || os === "android") {
    if (longSide >= 1024 && shortSide >= 768) return "tablet";
    return "mobile";
  }
  if (shortSide < 640) return "mobile";
  if (shortSide < 1024) return "tablet";
  return "desktop";
}

function getFamily(os: PlatformOS): PlatformFamily {
  if (os === "ios" || os === "macos") return "apple";
  if (os === "android") return "android";
  if (os === "windows") return "windows";
  return "other";
}

function getSafeArea(os: PlatformOS, standalone: boolean): { top: number; bottom: number } {
  if (os !== "ios" && os !== "macos") return { top: 0, bottom: 0 };
  const top = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sat") || "0", 10) || 0;
  const bottom = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sab") || "0", 10) || 0;
  if (standalone) {
    return { top: Math.max(top, 44), bottom: Math.max(bottom, 34) };
  }
  return { top, bottom };
}

function buildPlatformInfo(): PlatformInfo {
  const os = detectOS();
  const device = detectDevice(os, window.innerWidth, window.innerHeight);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
  const safeArea = getSafeArea(os, standalone);

  return {
    os,
    family: getFamily(os),
    device,
    standalone,
    touch: "ontouchstart" in window || navigator.maxTouchPoints > 0,
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    highContrast: window.matchMedia("(prefers-contrast: more)").matches,
    darkMode: window.matchMedia("(prefers-color-scheme: dark)").matches,
    safeAreaTop: safeArea.top,
    safeAreaBottom: safeArea.bottom,
    screenWidth: window.innerWidth,
    screenHeight: window.innerHeight,
    isPWA: standalone,
    isMobile: device === "mobile" || device === "tablet",
    isDesktop: device === "desktop",
  };
}

export function usePlatform(): PlatformInfo {
  const [info, setInfo] = useState<PlatformInfo>(buildPlatformInfo);

  useEffect(() => {
    const onResize = () => setInfo(buildPlatformInfo());
    const onChange = () => setInfo(buildPlatformInfo());

    window.addEventListener("resize", onResize);
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", onChange);
    window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", onChange);

    return () => {
      window.removeEventListener("resize", onResize);
      window.matchMedia("(prefers-color-scheme: dark)").removeEventListener("change", onChange);
      window.matchMedia("(prefers-reduced-motion: reduce)").removeEventListener("change", onChange);
    };
  }, []);

  return info;
}

export function useHaptics() {
  const trigger = useCallback((type: "light" | "medium" | "heavy" | "success" | "warning" | "error" = "light") => {
    if (typeof navigator === "undefined" || !navigator.vibrate) return;
    const patterns: Record<string, number[]> = {
      light: [8],
      medium: [15],
      heavy: [25],
      success: [10, 50, 10],
      warning: [20, 40, 20],
      error: [30, 60, 30, 60, 30],
    };
    navigator.vibrate(patterns[type] || patterns.light);
  }, []);

  return trigger;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
