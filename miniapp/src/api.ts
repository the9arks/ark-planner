const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8081";
// Fallback used only outside real Telegram (local browser preview during dev).
const DEV_TG_ID = import.meta.env.VITE_DEV_TG_ID ?? "1027565844";

declare global {
  interface Window {
    Telegram?: { WebApp?: { initData: string } };
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const initData = window.Telegram?.WebApp?.initData;
  const url = new URL(`${API_URL}${path}`);
  const headers: Record<string, string> = {};

  if (initData) {
    headers.Authorization = `tma ${initData}`;
  } else {
    url.searchParams.set("tg_id", DEV_TG_ID);
  }

  const res = await fetch(url.toString(), { headers });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export interface Digest {
  user: { is_pro: boolean };
  digest: {
    tasks_today: number;
    notes_today: number;
    meetings_today: number;
    money_today: number;
    food_today: number;
  };
}

export function getDigest() {
  return apiGet<Digest>("/api/digest");
}

export function getSection<T = Record<string, unknown>>(section: string) {
  return apiGet<{ items: T[] }>(`/api/${section}`);
}
