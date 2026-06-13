"use client";
import * as React from "react";
import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import { useServerInsertedHTML } from "next/navigation";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { lightTheme, darkTheme } from "@/lib/mui-theme";
import { useThemeMode } from "./theme-mode";

export function EmotionRegistry({ children }: { children: React.ReactNode }) {
  const [registry] = React.useState(() => {
    const cache = createCache({ key: "mui" });
    cache.compat = true;
    const prevInsert = cache.insert;
    let inserted: string[] = [];
    cache.insert = (...args) => {
      const serialized = args[1];
      if (cache.inserted[serialized.name] === undefined) {
        inserted.push(serialized.name);
      }
      return prevInsert(...args);
    };
    const flush = () => {
      const prevInserted = inserted;
      inserted = [];
      return prevInserted;
    };
    return { cache, flush };
  });

  useServerInsertedHTML(() => {
    const names = registry.flush();
    if (names.length === 0) return null;
    let styles = "";
    for (const name of names) {
      styles += registry.cache.inserted[name];
    }
    return (
      <style
        key={registry.cache.key}
        data-emotion={`${registry.cache.key} ${names.join(" ")}`}
        dangerouslySetInnerHTML={{ __html: styles }}
      />
    );
  });

  const { mode } = useThemeMode();
  return (
    <CacheProvider value={registry.cache}>
      <ThemeProvider theme={mode === "dark" ? darkTheme : lightTheme}>
        <CssBaseline enableColorScheme={false} />
        {children}
      </ThemeProvider>
    </CacheProvider>
  );
}
