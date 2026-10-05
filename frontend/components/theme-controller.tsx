"use client";

import { useEffect } from "react";

const THEME_EVENT = "olympus:theme-changed";

function automaticTheme(date = new Date()) {
  const hour = date.getHours();
  return hour >= 6 && hour < 18 ? "light" : "dark";
}

function applyAutomaticTheme() {
  const theme = automaticTheme();
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.classList.toggle("light", theme === "light");
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function ThemeController() {
  useEffect(() => {
    applyAutomaticTheme();
    const interval = window.setInterval(applyAutomaticTheme, 60_000);
    const refresh = () => applyAutomaticTheme();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

  return null;
}
