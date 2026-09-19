const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8081";
// Fallback used only outside real Telegram (local browser preview during dev).
const DEV_TG_ID = import.meta.env.VITE_DEV_TG_ID ?? "1027565844";

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string;
        ready: () => void;
        expand: () => void;
      };
    };
  }
}

function _authHeaders(url: URL): Record<string, string> {
  const initData = window.Telegram?.WebApp?.initData;
  const headers: Record<string, string> = {};
  if (initData) {
    headers.Authorization = `tma ${initData}`;
  } else {
    url.searchParams.set("tg_id", DEV_TG_ID);
  }
  return headers;
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  const headers = _authHeaders(url);
  const res = await fetch(url.toString(), { headers });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  const headers = _authHeaders(url);
  headers["Content-Type"] = "application/json";
  const res = await fetch(url.toString(), {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export type Tier = "free" | "pro" | "ultra";

export interface Digest {
  user: {
    tier: Tier;
    daily_ai_limit: number | null;
    morning_digest_time: string;
    breakfast_reminder_time: string;
    lunch_reminder_time: string;
    dinner_reminder_time: string;
    tz_offset: number;
  };
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

export function setTimeSetting(field: string, value: string) {
  return apiPost<{ ok: boolean }>("/api/settings/time", { field, value });
}

export function setTimezone(tz_offset: number) {
  return apiPost<{ ok: boolean }>("/api/settings/timezone", { tz_offset });
}

export interface EntryResult {
  ok: boolean;
  reply?: string;
  entry_type?: string;
  error?: string;
}

export async function submitEntry(text: string): Promise<EntryResult> {
  const url = new URL(`${API_URL}/api/entries`);
  const headers = _authHeaders(url);
  headers["Content-Type"] = "application/json";
  const res = await fetch(url.toString(), {
    method: "POST",
    headers,
    body: JSON.stringify({ text }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: data.error ?? "unknown_error" };
  }
  return { ok: true, reply: data.reply, entry_type: data.entry_type };
}
