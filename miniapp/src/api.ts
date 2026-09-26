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
        openTelegramLink: (url: string) => void;
        openLink: (url: string) => void;
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

export async function apiDelete<T>(path: string): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  const headers = _authHeaders(url);
  const res = await fetch(url.toString(), { method: "DELETE", headers });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export type Tier = "free" | "pro" | "ultra";

export interface Digest {
  user: {
    tier: Tier;
    daily_ai_limit: number | null;
    morning_digest_time: string | null;
    breakfast_reminder_time: string | null;
    lunch_reminder_time: string | null;
    dinner_reminder_time: string | null;
    money_reminder_time: string | null;
    daily_money_limit: number | null;
    sleep_goal_bedtime: string | null;
    sleep_goal_wake_time: string | null;
    tz_offset: number;
    money_goal_amount: number | null;
    tier_expires_at: string | null;
    had_subscription: boolean;
  };
  digest: {
    tasks_today: number;
    notes_today: number;
    meetings_today: number;
    money_today: number;
    food_today: number;
    rituals_today: number;
    sleep_hours_last: number | null;
    sleep_start_last: string | null;
    sleep_end_last: string | null;
    tasks_items: { id: string; title: string }[];
    notes_items: { id: string; content: string }[];
    meetings_items: { id: string; title: string; with_who: string | null; starts_at: string | null }[];
    money_items: { id: string; amount: number; category: string | null; direction: "expense" | "income" }[];
    food_items: { id: string; description: string | null; calories: number | null; created_at: string }[];
    habits_pending: string[];
    habits_total: number;
    sleep_items: { sleep_start: string | null; sleep_end: string | null; hours: number | null }[];
  };
}

export function getDigest() {
  return apiGet<Digest>("/api/digest");
}

export interface MoneySummary {
  today_total: number;
  month_total: number;
  income_today: number;
  expense_today: number;
  income_month: number;
  expense_month: number;
  goal_amount: number | null;
  daily_limit: number | null;
}

export function getMoneySummary() {
  return apiGet<MoneySummary>("/api/money/summary");
}

export function setMoneyGoal(amount: number | null) {
  return apiPost<{ ok: boolean }>("/api/money/goal", { amount });
}

export function setDailyMoneyLimit(amount: number | null) {
  return apiPost<{ ok: boolean }>("/api/money/daily-limit", { amount });
}

export interface HabitActionResult {
  ok: boolean;
  streak_days: number | null;
  reply: string;
}

export function checkinHabit(habitId: string) {
  return apiPost<HabitActionResult>(`/api/habits/${habitId}/checkin`, {});
}

export function relapseHabit(habitId: string) {
  return apiPost<HabitActionResult>(`/api/habits/${habitId}/relapse`, {});
}

export function deleteHabit(habitId: string) {
  return apiDelete<{ ok: boolean }>(`/api/habits/${habitId}`);
}

export interface FoodSummary {
  calories_today: number;
  goal: number | null;
}

export function getFoodSummary() {
  return apiGet<FoodSummary>("/api/food/summary");
}

export function setFoodGoal(amount: number | null) {
  return apiPost<{ ok: boolean }>("/api/food/goal", { amount });
}

export function addTaskManual(title: string) {
  return apiPost<{ ok: boolean; task: unknown }>("/api/tasks/manual", { title });
}

export function cancelMeeting(meetingId: string) {
  return apiDelete<{ ok: boolean }>(`/api/meetings/${meetingId}`);
}

export function completeTask(taskId: string, done: boolean = true) {
  return apiPost<{ ok: boolean }>(`/api/tasks/${taskId}/done`, { done });
}

export function updateTask(taskId: string, fields: { title?: string; due_at?: string | null }) {
  return apiPost<{ ok: boolean }>(`/api/tasks/${taskId}/update`, fields);
}

export function deleteNote(noteId: string) {
  return apiDelete<{ ok: boolean }>(`/api/notes/${noteId}`);
}

export function deleteMoneyEntry(entryId: string) {
  return apiDelete<{ ok: boolean }>(`/api/money/${entryId}`);
}

export function addSleepManual(sleepStart: string | null, sleepEnd: string | null) {
  return apiPost<{ ok: boolean; entry: unknown }>("/api/sleep/manual", {
    sleep_start: sleepStart,
    sleep_end: sleepEnd,
  });
}

export function updateSleep(sleepId: string, fields: { sleep_start?: string | null; sleep_end?: string | null }) {
  return apiPost<{ ok: boolean }>(`/api/sleep/${sleepId}/update`, fields);
}

export function deleteSleep(sleepId: string) {
  return apiDelete<{ ok: boolean }>(`/api/sleep/${sleepId}`);
}

export function rescheduleMeeting(meetingId: string, startsAt: string) {
  return apiPost<{ ok: boolean; meeting: unknown }>(`/api/meetings/${meetingId}/reschedule`, {
    starts_at: startsAt,
  });
}

export function updateMeeting(meetingId: string, fields: { with_who?: string; title?: string }) {
  return apiPost<{ ok: boolean }>(`/api/meetings/${meetingId}/update`, fields);
}

export interface OrderResult {
  url?: string;
  amount?: number;
  error?: string;
}

export async function createOrder(tier: string, period: string, promoCode?: string): Promise<OrderResult> {
  const url = new URL(`${API_URL}/api/orders`);
  const headers = _authHeaders(url);
  headers["Content-Type"] = "application/json";
  const res = await fetch(url.toString(), {
    method: "POST",
    headers,
    body: JSON.stringify({ tier, period, promo_code: promoCode }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { error: data.error ?? "unknown_error" };
  }
  return data;
}

export interface SubscriptionStatus {
  required: boolean;
  subscribed: boolean;
  channel_url: string | null;
}

export function getSubscriptionStatus() {
  return apiGet<SubscriptionStatus>("/api/subscription/status");
}

export function recheckSubscription() {
  return apiPost<{ subscribed: boolean }>("/api/subscription/recheck", {});
}

export async function claimTrial(): Promise<boolean> {
  try {
    const res = await apiPost<{ granted: boolean }>("/api/trial/claim", {});
    return res.granted;
  } catch {
    return false;
  }
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
  try {
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
  } catch {
    // Network failure, dropped connection, or the backend waking up from
    // Render's free-tier cold start — never let this hang the composer forever.
    return { ok: false, error: "network_error" };
  }
}
