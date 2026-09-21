import { useEffect, useState } from "react";
import {
  addTaskManual,
  cancelMeeting,
  checkinHabit,
  claimTrial,
  createOrder,
  getDigest,
  getFoodSummary,
  getMoneySummary,
  getSection,
  getSubscriptionStatus,
  recheckSubscription,
  relapseHabit,
  rescheduleMeeting,
  setFoodGoal,
  setMoneyGoal,
  setTimeSetting,
  setTimezone,
  submitEntry,
  type Digest,
  type FoodSummary,
  type MoneySummary,
  type SubscriptionStatus,
  type Tier,
} from "./api";

type TabId =
  | "digest"
  | "tasks"
  | "notes"
  | "money"
  | "meetings"
  | "food"
  | "rituals"
  | "settings";

const TABS: { id: TabId; num: string; label: string }[] = [
  { id: "digest", num: "01", label: "Сегодня" },
  { id: "tasks", num: "02", label: "Задачи" },
  { id: "notes", num: "03", label: "Заметки" },
  { id: "money", num: "04", label: "Деньги" },
  { id: "meetings", num: "05", label: "Встречи" },
  { id: "food", num: "06", label: "Еда" },
  { id: "rituals", num: "07", label: "Привычки" },
  { id: "settings", num: "08", label: "Настройки" },
];

function ArkMark({ size = 36 }: { size?: number }) {
  return (
    <img
      src="/ark-logo.jpg"
      alt="ARK"
      width={size}
      height={size}
      className="rounded-lg object-cover"
      style={{ width: size, height: size }}
    />
  );
}

function Card({
  title,
  hint,
  children,
  onClick,
}: {
  title: string;
  hint?: string;
  children?: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-2xl border border-white/10 bg-white/[0.03] p-4 flex flex-col gap-2 min-h-[110px]${
        onClick ? " active:bg-white/[0.06] active:scale-[0.98] transition-transform cursor-pointer" : ""
      }`}
    >
      <span className="text-[11px] uppercase tracking-wider text-white/40">
        {title}
      </span>
      {children ?? (
        <div className="flex-1 flex items-center">
          <span className="text-white/30 text-sm">{hint}</span>
        </div>
      )}
    </div>
  );
}

function CountCard({
  title,
  count,
  hint,
  onClick,
}: {
  title: string;
  count: number;
  hint: string;
  onClick: () => void;
}) {
  return (
    <Card title={title} onClick={onClick}>
      {count > 0 ? (
        <div className="flex-1 flex items-end">
          <span className="text-3xl font-semibold">{count}</span>
          <span className="text-white/30 text-sm ml-1 mb-1">сегодня</span>
        </div>
      ) : (
        <div className="flex-1 flex items-center">
          <span className="text-white/30 text-sm">{hint}</span>
        </div>
      )}
    </Card>
  );
}

const MOTIVATIONAL_PHRASES = [
  "Проживём сегодня чуть лучше, чем вчера.",
  "Маленькие шаги каждый день — большой путь за год.",
  "Ты уже здесь и уже начал — остальное приложится.",
  "Один день — один шаг вперёд.",
  "Прогресс важнее идеала.",
  "Сфокусируйся на главном, остальное подождёт.",
  "Заботиться о себе — тоже дело, и важное.",
  "Сегодня — хороший день, чтобы не откладывать.",
];

function pickMotivation(): string {
  return MOTIVATIONAL_PHRASES[Math.floor(Math.random() * MOTIVATIONAL_PHRASES.length)];
}

function DigestView({ digest, onNavigate }: { digest: Digest | null; onNavigate: (tab: TabId) => void }) {
  const [greeting] = useState(pickMotivation);
  const today = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const d = digest?.digest;
  const hasAny =
    !!d &&
    (d.tasks_today || d.notes_today || d.meetings_today || d.money_today || d.food_today || d.rituals_today);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl bg-gradient-to-br from-white/[0.06] to-white/[0.01] border border-white/10 p-5">
        <div className="text-white/40 text-sm capitalize">{today}</div>
        <div className="text-xl font-semibold mt-1">{greeting}</div>
        <div className="text-white/50 text-sm mt-2">
          {hasAny
            ? "Вот что уже записано сегодня."
            : "Записей пока нет — надиктуй или напиши, что происходит."}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <CountCard
          title="Задачи"
          count={d?.tasks_today ?? 0}
          hint="Добавить первую"
          onClick={() => onNavigate("tasks")}
        />
        <CountCard
          title="Заметки"
          count={d?.notes_today ?? 0}
          hint="Мысль или запись"
          onClick={() => onNavigate("notes")}
        />
        <CountCard
          title="Встречи"
          count={d?.meetings_today ?? 0}
          hint="Запланировать"
          onClick={() => onNavigate("meetings")}
        />
        <CountCard
          title="Еда"
          count={d?.food_today ?? 0}
          hint="Сфоткай еду"
          onClick={() => onNavigate("food")}
        />
        <CountCard
          title="Привычки"
          count={d?.rituals_today ?? 0}
          hint="Отметь сегодня"
          onClick={() => onNavigate("rituals")}
        />
        <CountCard
          title="Деньги"
          count={d?.money_today ?? 0}
          hint="Настрой бюджет"
          onClick={() => onNavigate("money")}
        />
      </div>
    </div>
  );
}

function ListView<T extends { id: string; created_at: string }>({
  section,
  emptyLabel,
  emptyHint,
  render,
}: {
  section: string;
  emptyLabel: string;
  emptyHint: string;
  render: (item: T) => { title: string; subtitle?: string };
}) {
  const [items, setItems] = useState<T[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSection<T>(section)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [section]);

  if (items === null) {
    return <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>;
  }
  if (items.length === 0) {
    return <EmptyView label={emptyLabel} hint={emptyHint} />;
  }

  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => {
        const { title, subtitle } = render(item);
        return (
          <div
            key={item.id}
            className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
          >
            <div className="text-sm">{title}</div>
            {subtitle && <div className="text-white/40 text-xs mt-1">{subtitle}</div>}
          </div>
        );
      })}
    </div>
  );
}

function EmptyView({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-3 py-20">
      <div className="text-white/20">
        <ArkMark size={32} />
      </div>
      <div className="text-white/60">{label}</div>
      <div className="text-white/30 text-sm max-w-[240px]">{hint}</div>
    </div>
  );
}

function ComposerBar({ onSubmitted }: { onSubmitted: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setToast(null);
    const result = await submitEntry(trimmed);
    setBusy(false);
    if (result.ok) {
      setText("");
      setToast(result.reply ?? "Записал");
      onSubmitted();
    } else if (result.error === "quota_exceeded") {
      setToast("Лимит AI-действий на сегодня исчерпан — загляни в «Настройки» за тарифом");
    } else if (result.error === "not_subscribed") {
      setToast("Нужна подписка на канал ARK PLANNER — перезайди в приложение");
      onSubmitted();
    } else if (result.error === "service_unavailable") {
      setToast("⚠️ ARK временно недоступен (технические работы) — попробуй через несколько минут");
    } else if (result.error === "network_error") {
      setToast("Не достучались до сервера (возможно, он просыпался) — попробуй ещё раз");
    } else {
      setToast("Не получилось записать, попробуй ещё раз");
    }
    setTimeout(() => setToast(null), 4000);
  }

  return (
    <div className="mx-auto max-w-[420px] px-4">
      {toast && (
        <div className="mb-2 rounded-xl border border-white/10 bg-[#0f0f12]/95 backdrop-blur px-4 py-2 text-xs text-white/70">
          {toast}
        </div>
      )}
      <div className="flex items-center gap-2 rounded-full border border-white/10 bg-[#0f0f12]/95 backdrop-blur px-4 py-3">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
          disabled={busy}
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-white/30"
          placeholder="Напиши что-нибудь…"
        />
        <button
          onClick={handleSubmit}
          disabled={busy || !text.trim()}
          className="w-8 h-8 rounded-full bg-white text-black text-sm grid place-items-center disabled:opacity-40"
        >
          {busy ? "…" : "→"}
        </button>
      </div>
    </div>
  );
}

function formatWhen(iso?: string | null): string {
  if (!iso) return "";
  const dt = new Date(iso);
  const today = new Date();
  const sameDay = dt.toDateString() === today.toDateString();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const time = dt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (sameDay) return `сегодня в ${time}`;
  if (dt.toDateString() === tomorrow.toDateString()) return `завтра в ${time}`;
  return dt.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) + ` в ${time}`;
}

interface Task { id: string; created_at: string; title: string; due_at: string | null }
interface Note { id: string; created_at: string; content: string }
interface Meeting { id: string; created_at: string; title: string; with_who: string | null; starts_at: string | null }
interface MoneyEntry { id: string; created_at: string; amount: number; category: string | null; comment: string | null }
interface FoodEntry { id: string; created_at: string; description: string | null; calories: number | null }
interface Habit {
  id: string;
  created_at: string;
  title: string;
  habit_type: "build" | "quit";
  days_of_week: string[] | null;
  start_time: string | null;
  streak_start_date: string | null;
  current_streak: number;
}

const WEEKDAY_RU_SHORT: Record<string, string> = {
  mon: "Пн", tue: "Вт", wed: "Ср", thu: "Чт", fri: "Пт", sat: "Сб", sun: "Вс",
};

function HabitCard({
  habit,
  onAction,
}: {
  habit: Habit;
  onAction: (habitId: string, kind: "checkin" | "relapse") => Promise<void>;
}) {
  const isQuit = habit.habit_type === "quit";
  const days = habit.current_streak;
  const schedule =
    habit.days_of_week && habit.start_time
      ? habit.days_of_week.map((d) => WEEKDAY_RU_SHORT[d] ?? d).join(", ") +
        ` · ${habit.start_time.slice(0, 5)}`
      : null;
  const [busy, setBusy] = useState(false);

  async function handle(kind: "checkin" | "relapse") {
    setBusy(true);
    try {
      await onAction(habit.id, kind);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="text-sm">{habit.title}</div>
          {schedule && <div className="text-white/40 text-xs">{schedule}</div>}
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-semibold">{days}</div>
          <div className="text-white/30 text-[10px]">{isQuit ? "дней без срыва" : "дней подряд"}</div>
        </div>
      </div>
      <div className="flex gap-2">
        {isQuit ? (
          <>
            <button
              disabled={busy}
              onClick={() => handle("checkin")}
              className="flex-1 rounded-lg bg-white/10 text-xs py-2 disabled:opacity-50"
            >
              Держусь
            </button>
            <button
              disabled={busy}
              onClick={() => handle("relapse")}
              className="flex-1 rounded-lg bg-white/5 text-white/60 text-xs py-2 disabled:opacity-50"
            >
              Сорвался
            </button>
          </>
        ) : (
          <button
            disabled={busy}
            onClick={() => handle("checkin")}
            className="flex-1 rounded-lg bg-white/10 text-xs py-2 disabled:opacity-50"
          >
            Отметить сегодня
          </button>
        )}
      </div>
    </div>
  );
}

function HabitsView({ refreshTick, onChanged }: { refreshTick: number; onChanged: () => void }) {
  const [habits, setHabits] = useState<Habit[] | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSection<Habit>("rituals")
      .then((res) => {
        if (!cancelled) setHabits(res.items);
      })
      .catch(() => {
        if (!cancelled) setHabits([]);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  async function handleAction(habitId: string, kind: "checkin" | "relapse") {
    try {
      const result = kind === "checkin" ? await checkinHabit(habitId) : await relapseHabit(habitId);
      setToast(result.reply);
      setHabits((prev) =>
        prev
          ? prev.map((h) =>
              h.id === habitId ? { ...h, current_streak: result.streak_days ?? h.current_streak } : h
            )
          : prev
      );
      onChanged();
    } catch {
      setToast("Не получилось, попробуй ещё раз");
    }
    setTimeout(() => setToast(null), 4000);
  }

  if (habits === null) {
    return <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>;
  }
  if (habits.length === 0) {
    return (
      <EmptyView
        label="Привычек пока нет"
        hint="«Тренировка бокс пн ср пт в 18:00, напомни за час» — или «хочу бросить курить»"
      />
    );
  }

  const building = habits.filter((h) => h.habit_type !== "quit");
  const quitting = habits.filter((h) => h.habit_type === "quit");

  return (
    <div className="flex flex-col gap-4">
      {toast && (
        <div className="rounded-xl border border-white/10 bg-[#0f0f12]/95 backdrop-blur px-4 py-2 text-xs text-white/70">
          {toast}
        </div>
      )}
      {building.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] uppercase tracking-wider text-white/40">🎯 Привычки</div>
          {building.map((h) => (
            <HabitCard key={h.id} habit={h} onAction={handleAction} />
          ))}
        </div>
      )}
      {quitting.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] uppercase tracking-wider text-white/40">🚭 Отказы</div>
          {quitting.map((h) => (
            <HabitCard key={h.id} habit={h} onAction={handleAction} />
          ))}
        </div>
      )}
    </div>
  );
}

function MoneyView({ refreshTick }: { refreshTick: number }) {
  const [summary, setSummary] = useState<MoneySummary | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalInput, setGoalInput] = useState("");
  const [savingGoal, setSavingGoal] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMoneySummary()
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  async function saveGoal() {
    const trimmed = goalInput.trim();
    const amount = trimmed ? Number(trimmed) : null;
    if (trimmed && (!amount || amount <= 0)) return;
    setSavingGoal(true);
    setGoalError(null);
    try {
      await setMoneyGoal(amount);
      setSummary((prev) => (prev ? { ...prev, goal_amount: amount } : prev));
      setEditingGoal(false);
    } catch {
      setGoalError("Не получилось сохранить, попробуй ещё раз");
    } finally {
      setSavingGoal(false);
    }
  }

  const goalProgress =
    summary?.goal_amount && summary.goal_amount > 0
      ? Math.min(100, Math.round((summary.month_total / summary.goal_amount) * 100))
      : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <Card title="Сегодня">
          <div className="flex-1 flex items-end">
            <span className="text-2xl font-semibold">{summary ? `${summary.today_total}₽` : "…"}</span>
          </div>
        </Card>
        <Card title="Месяц">
          <div className="flex-1 flex items-end">
            <span className="text-2xl font-semibold">{summary ? `${summary.month_total}₽` : "…"}</span>
          </div>
        </Card>
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-white/40">Цель на месяц</span>
          {!editingGoal && (
            <button
              onClick={() => {
                setGoalInput(summary?.goal_amount ? String(summary.goal_amount) : "");
                setEditingGoal(true);
              }}
              className="text-xs text-white/50 underline"
            >
              {summary?.goal_amount ? "Изменить" : "Задать"}
            </button>
          )}
        </div>
        {editingGoal ? (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="number"
              inputMode="numeric"
              value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              placeholder="Например, 30000"
              className="flex-1 bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1.5 text-sm text-white"
            />
            <button
              onClick={saveGoal}
              disabled={savingGoal}
              className="rounded-lg bg-white text-black text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {savingGoal ? "…" : "OK"}
            </button>
          </div>
        ) : summary?.goal_amount ? (
          <>
            <div className="text-sm mt-2">
              {summary.month_total}₽ из {summary.goal_amount}₽
            </div>
            <div className="h-2 rounded-full bg-white/10 mt-2 overflow-hidden">
              <div
                className={`h-full rounded-full ${goalProgress! >= 100 ? "bg-red-400" : "bg-white"}`}
                style={{ width: `${goalProgress}%` }}
              />
            </div>
          </>
        ) : (
          <div className="text-white/30 text-sm mt-2">Не задана — сколько хочешь тратить в месяц?</div>
        )}
        {goalError && <div className="text-red-400/80 text-xs mt-2">{goalError}</div>}
      </div>

      <ListView<MoneyEntry>
        key={refreshTick}
        section="money"
        emptyLabel="Трат пока нет"
        emptyHint="Пришли фото чека — занесу автоматически"
        render={(m) => ({
          title: `${m.amount}₽ ${m.category ?? ""}`,
          subtitle: m.comment ?? undefined,
        })}
      />
    </div>
  );
}

function toDatetimeLocalValue(iso: string): string {
  const dt = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function TasksView({ refreshTick, onChanged }: { refreshTick: number; onChanged: () => void }) {
  const [items, setItems] = useState<Task[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSection<Task>("tasks")
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  async function handleAdd() {
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await addTaskManual(trimmed);
      setTitle("");
      setAdding(false);
      onChanged();
    } catch {
      setError("Не получилось добавить, попробуй ещё раз");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {adding ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 flex flex-col gap-2">
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            placeholder="Например, купить молоко"
            className="bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
          />
          <div className="flex gap-2">
            <button
              disabled={busy || !title.trim()}
              onClick={handleAdd}
              className="flex-1 rounded-lg bg-white text-black text-xs py-2 disabled:opacity-50"
            >
              {busy ? "…" : "Добавить"}
            </button>
            <button
              onClick={() => {
                setAdding(false);
                setTitle("");
              }}
              className="flex-1 rounded-lg bg-white/5 text-white/60 text-xs py-2"
            >
              Отмена
            </button>
          </div>
          {error && <div className="text-red-400/80 text-xs">{error}</div>}
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="rounded-xl border border-white/10 bg-white/[0.03] text-sm py-3 text-white/60"
        >
          + Добавить задачу
        </button>
      )}

      {items === null ? (
        <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>
      ) : items.length === 0 ? (
        <EmptyView label="Задач пока нет" hint="Напиши боту: «купить молоко завтра» или добавь кнопкой выше" />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((t) => (
            <div key={t.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="text-sm">{t.title}</div>
              {t.due_at && <div className="text-white/40 text-xs mt-1">{formatWhen(t.due_at)}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MeetingCard({
  meeting,
  isPast,
  onChanged,
}: {
  meeting: Meeting;
  isPast: boolean;
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [rescheduling, setRescheduling] = useState(false);
  const [newTime, setNewTime] = useState(meeting.starts_at ? toDatetimeLocalValue(meeting.starts_at) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCancel() {
    setBusy(true);
    setError(null);
    try {
      await cancelMeeting(meeting.id);
      onChanged();
      setBusy(false);
      setExpanded(false);
    } catch {
      setError("Не получилось отменить, попробуй ещё раз");
      setBusy(false);
    }
  }

  async function handleReschedule() {
    if (!newTime) return;
    setBusy(true);
    setError(null);
    try {
      await rescheduleMeeting(meeting.id, new Date(newTime).toISOString());
      onChanged();
      setBusy(false);
      setRescheduling(false);
      setExpanded(false);
    } catch {
      setError("Не получилось перенести, попробуй ещё раз");
      setBusy(false);
    }
  }

  return (
    <div className={`rounded-xl border border-white/10 bg-white/[0.03] p-3 ${isPast ? "opacity-40" : ""}`}>
      <button
        className="w-full text-left"
        onClick={() => !isPast && setExpanded((e) => !e)}
        disabled={isPast}
      >
        <div className="text-sm">
          {meeting.with_who ? `Встреча с ${meeting.with_who}` : meeting.title}
          {isPast && " ✓"}
        </div>
        {meeting.starts_at && (
          <div className="text-white/40 text-xs mt-1">
            {formatWhen(meeting.starts_at)}
            {isPast ? " · прошла" : ""}
          </div>
        )}
      </button>
      {!isPast && expanded && (
        <div className="mt-3 flex flex-col gap-2">
          {rescheduling ? (
            <div className="flex items-center gap-2">
              <input
                type="datetime-local"
                value={newTime}
                onChange={(e) => setNewTime(e.target.value)}
                className="flex-1 bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white [color-scheme:dark]"
              />
              <button
                disabled={busy || !newTime}
                onClick={handleReschedule}
                className="rounded-lg bg-white text-black text-xs px-3 py-1.5 disabled:opacity-50"
              >
                {busy ? "…" : "OK"}
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={() => setRescheduling(true)}
                className="flex-1 rounded-lg bg-white/10 text-xs py-2 disabled:opacity-50"
              >
                Перенести
              </button>
              <button
                disabled={busy}
                onClick={handleCancel}
                className="flex-1 rounded-lg bg-white/5 text-white/60 text-xs py-2 disabled:opacity-50"
              >
                {busy ? "…" : "Отменить"}
              </button>
            </div>
          )}
          {error && <div className="text-red-400/80 text-xs">{error}</div>}
        </div>
      )}
    </div>
  );
}

function MeetingsView({ refreshTick, onChanged }: { refreshTick: number; onChanged: () => void }) {
  const [items, setItems] = useState<Meeting[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSection<Meeting>("meetings")
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  if (items === null) {
    return <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>;
  }
  if (items.length === 0) {
    return <EmptyView label="Встреч пока нет" hint="Напиши: «завтра в 15:00 встреча с Андреем»" />;
  }

  const now = new Date();

  return (
    <div className="flex flex-col gap-2">
      {items.map((m) => (
        <MeetingCard
          key={m.id}
          meeting={m}
          isPast={m.starts_at ? new Date(m.starts_at) < now : false}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}

const MEAL_BUCKETS: { key: string; label: string; from: number; to: number }[] = [
  { key: "breakfast", label: "Завтрак", from: 0, to: 11 },
  { key: "lunch", label: "Обед", from: 11, to: 17 },
  { key: "dinner", label: "Ужин", from: 17, to: 24 },
];

function FoodView({ refreshTick }: { refreshTick: number }) {
  const [items, setItems] = useState<FoodEntry[] | null>(null);
  const [summary, setSummary] = useState<FoodSummary | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalInput, setGoalInput] = useState("");
  const [savingGoal, setSavingGoal] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSection<FoodEntry>("food")
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    getFoodSummary()
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  async function saveGoal() {
    const trimmed = goalInput.trim();
    const amount = trimmed ? Number(trimmed) : null;
    if (trimmed && (!amount || amount <= 0)) return;
    setSavingGoal(true);
    setGoalError(null);
    try {
      await setFoodGoal(amount);
      setSummary((prev) => (prev ? { ...prev, goal: amount } : prev));
      setEditingGoal(false);
    } catch {
      setGoalError("Не получилось сохранить, попробуй ещё раз");
    } finally {
      setSavingGoal(false);
    }
  }

  const goalProgress =
    summary?.goal && summary.goal > 0 ? Math.min(100, Math.round((summary.calories_today / summary.goal) * 100)) : null;

  const today = new Date().toDateString();
  const buckets: Record<string, FoodEntry[]> = { breakfast: [], lunch: [], dinner: [], other: [] };
  (items ?? []).forEach((f) => {
    const dt = new Date(f.created_at);
    if (dt.toDateString() !== today) {
      buckets.other.push(f);
      return;
    }
    const hour = dt.getHours();
    const bucket = MEAL_BUCKETS.find((b) => hour >= b.from && hour < b.to);
    buckets[bucket?.key ?? "other"].push(f);
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-white/40">Цель по калориям в день</span>
          {!editingGoal && (
            <button
              onClick={() => {
                setGoalInput(summary?.goal ? String(summary.goal) : "");
                setEditingGoal(true);
              }}
              className="text-xs text-white/50 underline"
            >
              {summary?.goal ? "Изменить" : "Задать"}
            </button>
          )}
        </div>
        {editingGoal ? (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="number"
              inputMode="numeric"
              value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              placeholder="Например, 2000"
              className="flex-1 bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1.5 text-sm text-white"
            />
            <button
              onClick={saveGoal}
              disabled={savingGoal}
              className="rounded-lg bg-white text-black text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {savingGoal ? "…" : "OK"}
            </button>
          </div>
        ) : summary?.goal ? (
          <>
            <div className="text-sm mt-2">
              {summary.calories_today} ккал из {summary.goal} ккал
            </div>
            <div className="h-2 rounded-full bg-white/10 mt-2 overflow-hidden">
              <div
                className={`h-full rounded-full ${goalProgress! >= 100 ? "bg-red-400" : "bg-white"}`}
                style={{ width: `${goalProgress}%` }}
              />
            </div>
          </>
        ) : (
          <div className="text-white/30 text-sm mt-2">Не задана — сколько килокалорий в день твоя цель?</div>
        )}
        {goalError && <div className="text-red-400/80 text-xs mt-2">{goalError}</div>}
      </div>

      {items === null ? (
        <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>
      ) : items.length === 0 ? (
        <EmptyView label="Приёмов пищи пока нет" hint="Сфоткай тарелку — посчитаю калории и БЖУ" />
      ) : (
        <>
          {MEAL_BUCKETS.map((b) =>
            buckets[b.key].length > 0 ? (
              <div key={b.key} className="flex flex-col gap-2">
                <div className="text-[11px] uppercase tracking-wider text-white/40">{b.label}</div>
                {buckets[b.key].map((f) => (
                  <div key={f.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="text-sm">{f.description ?? "Приём пищи"}</div>
                    {f.calories && <div className="text-white/40 text-xs mt-1">~{f.calories} ккал</div>}
                  </div>
                ))}
              </div>
            ) : null
          )}
          {buckets.other.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="text-[11px] uppercase tracking-wider text-white/40">Раньше</div>
              {buckets.other.map((f) => (
                <div key={f.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <div className="text-sm">{f.description ?? "Приём пищи"}</div>
                  {f.calories && <div className="text-white/40 text-xs mt-1">~{f.calories} ккал</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const TIER_LABELS: Record<Tier, string> = { free: "Free", pro: "Pro", ultra: "Ultra" };

function TimeRow({
  label,
  field,
  value,
  onSaved,
}: {
  label: string;
  field: string;
  value: string;
  onSaved: (field: string, value: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  return (
    <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="text-sm">
        {label}
        {error && <span className="text-red-400/80 text-xs ml-2">не сохранилось, попробуй ещё раз</span>}
      </span>
      <input
        type="time"
        defaultValue={value?.slice(0, 5)}
        disabled={saving}
        onChange={async (e) => {
          const next = e.target.value;
          if (!next) return;
          setSaving(true);
          setError(false);
          try {
            await setTimeSetting(field, next);
            onSaved(field, next);
          } catch {
            setError(true);
          } finally {
            setSaving(false);
          }
        }}
        className="bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1 text-sm text-white [color-scheme:dark]"
      />
    </div>
  );
}

const TZ_OPTIONS = Array.from({ length: 27 }, (_, i) => i - 12); // UTC-12 .. UTC+14

function TimezoneRow({
  value,
  onSaved,
}: {
  value: number;
  onSaved: (tz: number) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  return (
    <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="text-sm">
        Часовой пояс
        {error && <span className="text-red-400/80 text-xs ml-2">не сохранилось</span>}
      </span>
      <select
        value={value}
        disabled={saving}
        onChange={async (e) => {
          const tz = Number(e.target.value);
          setSaving(true);
          setError(false);
          try {
            await setTimezone(tz);
            onSaved(tz);
          } catch {
            setError(true);
          } finally {
            setSaving(false);
          }
        }}
        className="bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1 text-sm text-white [color-scheme:dark]"
      >
        {TZ_OPTIONS.map((tz) => (
          <option key={tz} value={tz}>
            UTC{tz >= 0 ? "+" : ""}{tz}
          </option>
        ))}
      </select>
    </div>
  );
}

const TARIFF_OPTIONS: {
  tier: "pro" | "ultra";
  period: "month" | "year" | "lifetime";
  label: string;
  wasPrice: string;
  price: string;
}[] = [
  { tier: "pro", period: "month", label: "Pro / мес", wasPrice: "399₽", price: "199₽" },
  { tier: "ultra", period: "month", label: "Ultra / мес", wasPrice: "1199₽", price: "599₽" },
  { tier: "pro", period: "year", label: "Pro / год", wasPrice: "3990₽", price: "1990₽" },
  { tier: "ultra", period: "year", label: "Ultra / год", wasPrice: "11990₽", price: "5990₽" },
  { tier: "pro", period: "lifetime", label: "Pro навсегда", wasPrice: "9990₽", price: "4990₽" },
  { tier: "ultra", period: "lifetime", label: "Ultra навсегда", wasPrice: "19990₽", price: "9990₽" },
];

function openExternal(url: string) {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.openLink) {
    webApp.openLink(url);
  } else {
    window.open(url, "_blank");
  }
}

function TariffPurchase() {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPromo, setShowPromo] = useState(false);
  const [promoCode, setPromoCode] = useState("");

  async function buy(tier: string, period: string) {
    const key = `${tier}_${period}`;
    setBusyKey(key);
    setError(null);
    try {
      const result = await createOrder(tier, period, promoCode.trim() || undefined);
      if (result.url) {
        openExternal(result.url);
      } else if (result.error === "not_configured") {
        setError("Оплата подключается, скоро будет доступна 🙌 Загляни чуть позже.");
      } else if (result.error === "invalid_promo") {
        setError("Такого промокода нет — проверь и попробуй ещё раз.");
      } else {
        setError("Не получилось создать оплату, попробуй ещё раз.");
      }
    } catch {
      setError("Не получилось создать оплату, попробуй ещё раз.");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 mt-4">
      <div className="text-center font-display font-bold text-lg leading-tight bg-gradient-to-r from-amber-200 via-white to-amber-200 bg-clip-text text-transparent">
        Включи ARK на полную ⚡️
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2 text-center">
          <div className="text-[10px] text-white/40 tracking-wide">FREE</div>
          <div className="font-display text-sm font-bold mt-1">0₽</div>
        </div>
        <div className="rounded-xl border border-amber-200/20 bg-gradient-to-b from-amber-400/[0.08] to-white/[0.02] p-2 text-center">
          <div className="text-[10px] text-white/60 tracking-wide">PRO</div>
          <div className="text-[10px] text-white/30 line-through">399₽</div>
          <div className="font-display text-base font-bold text-amber-200">199₽</div>
        </div>
        <div className="rounded-xl border border-amber-200/20 bg-gradient-to-b from-amber-400/[0.08] to-white/[0.02] p-2 text-center">
          <div className="text-[10px] text-white/60 tracking-wide">ULTRA</div>
          <div className="text-[10px] text-white/30 line-through">1199₽</div>
          <div className="font-display text-base font-bold text-amber-200">599₽</div>
        </div>
      </div>
      <div className="mx-auto rounded-full border border-amber-200/25 bg-amber-400/10 px-3 py-1 text-[11px] font-semibold tracking-wide text-amber-200">
        🔥 Скидка -50%
      </div>
      <div className="grid grid-cols-2 gap-2">
        {TARIFF_OPTIONS.map((opt) => {
          const key = `${opt.tier}_${opt.period}`;
          return (
            <button
              key={key}
              disabled={busyKey === key}
              onClick={() => buy(opt.tier, opt.period)}
              className="rounded-xl bg-white/[0.06] border border-white/10 text-xs py-2 px-2 disabled:opacity-50 flex flex-col items-center gap-0.5"
            >
              <span className="text-white/50">{opt.label}</span>
              {busyKey === key ? (
                <span>…</span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <span className="text-white/30 line-through">{opt.wasPrice}</span>
                  <span className="font-display font-bold text-amber-200">{opt.price}</span>
                </span>
              )}
            </button>
          );
        })}
      </div>
      {showPromo ? (
        <input
          type="text"
          value={promoCode}
          onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
          placeholder="Промокод"
          maxLength={6}
          className="rounded-lg bg-white/[0.06] border border-white/10 px-3 py-2 text-xs text-center tracking-widest uppercase placeholder:normal-case placeholder:tracking-normal"
        />
      ) : (
        <button onClick={() => setShowPromo(true)} className="text-white/40 text-xs underline underline-offset-2">
          Есть промокод?
        </button>
      )}
      {error && <div className="text-white/50 text-xs">{error}</div>}
    </div>
  );
}

function SettingsView({
  digest,
  onTimeSaved,
  onTzSaved,
}: {
  digest: Digest | null;
  onTimeSaved: (field: string, value: string) => void;
  onTzSaved: (tz: number) => void;
}) {
  if (!digest) {
    return <div className="text-white/30 text-sm text-center py-20">Загрузка…</div>;
  }
  const { user } = digest;
  const limitLabel = user.daily_ai_limit === null ? "безлимит" : `${user.daily_ai_limit} AI-действий/день`;

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl bg-gradient-to-br from-white/[0.06] to-white/[0.01] border border-white/10 p-5">
        <div className="text-white/40 text-sm">Тариф</div>
        <div className="text-2xl font-semibold mt-1">{TIER_LABELS[user.tier]}</div>
        <div className="text-white/50 text-sm mt-2">{limitLabel}</div>
        <TariffPurchase />
      </div>

      <TimezoneRow value={user.tz_offset} onSaved={onTzSaved} />

      <div className="text-[11px] uppercase tracking-wider text-white/40 mt-2">
        Время напоминаний
      </div>
      <TimeRow
        label="Утренний дайджест"
        field="morning_digest_time"
        value={user.morning_digest_time}
        onSaved={onTimeSaved}
      />
      <TimeRow
        label="Завтрак"
        field="breakfast_reminder_time"
        value={user.breakfast_reminder_time}
        onSaved={onTimeSaved}
      />
      <TimeRow
        label="Обед"
        field="lunch_reminder_time"
        value={user.lunch_reminder_time}
        onSaved={onTimeSaved}
      />
      <TimeRow
        label="Ужин"
        field="dinner_reminder_time"
        value={user.dinner_reminder_time}
        onSaved={onTimeSaved}
      />
    </div>
  );
}

const ONBOARDING_KEY = "ark_onboarding_seen";

const ONBOARDING_SLIDES = [
  {
    num: "01",
    title: "ARK — твоя жизнь в одном месте",
    text: "Задачи, привычки, встречи, еда и деньги — в одном спокойном месте. Всё начинается с дайджеста дня: открыл и сразу видно, что происходит.",
  },
  {
    num: "02",
    title: "Говори боту",
    text: "Надиктуй или напиши одной фразой — сам разложит по разделам: задачи, встречи со временем, еда с калориями, траты и мысли в заметки.",
  },
  {
    num: "03",
    title: "Фото и утро",
    text: "Сфоткай еду или чек — калории и траты посчитаются сами. А по утрам — дайджест с планом на день.",
  },
];

function SubscriptionGate({ channelUrl, onVerified }: { channelUrl: string | null; onVerified: () => void }) {
  const [checking, setChecking] = useState(false);
  const [denied, setDenied] = useState(false);

  function openChannel() {
    if (channelUrl) openExternal(channelUrl);
  }

  async function check() {
    setChecking(true);
    setDenied(false);
    try {
      const res = await recheckSubscription();
      if (res.subscribed) {
        onVerified();
      } else {
        setDenied(true);
      }
    } catch {
      setDenied(true);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 ark-gradient-bg flex flex-col items-center justify-center max-w-[480px] mx-auto px-6 text-center">
      <ArkMark size={48} />
      <div className="text-2xl font-semibold mt-5">Доступ по подписке</div>
      <div className="text-white/50 text-sm mt-3 leading-relaxed max-w-[320px]">
        Чтобы пользоваться ARK PLANNER, подпишись на наш Telegram-канал — там фичи, новости и бонусы
        для подписчиков.
      </div>
      <button
        onClick={openChannel}
        className="w-full max-w-[320px] rounded-xl bg-white text-black text-sm font-medium py-3 mt-8"
      >
        📢 Подписаться на канал
      </button>
      <button
        disabled={checking}
        onClick={check}
        className="w-full max-w-[320px] rounded-xl border border-white/15 text-white text-sm font-medium py-3 mt-3 disabled:opacity-50"
      >
        {checking ? "Проверяю…" : "✅ Я подписался, проверить"}
      </button>
      {denied && (
        <div className="text-white/40 text-xs mt-4 max-w-[280px]">
          Пока не вижу подписки — подожди пару секунд после вступления в канал и попробуй ещё раз.
        </div>
      )}
    </div>
  );
}

function TrialOffer({ onAccept, onSkip }: { onAccept: () => void; onSkip: () => void }) {
  const [claiming, setClaiming] = useState(false);

  return (
    <div className="fixed inset-0 z-50 ark-gradient-bg flex flex-col items-center justify-center max-w-[480px] mx-auto px-6 text-center">
      <div className="text-5xl mb-5">🎁</div>
      <div className="text-2xl font-semibold">Дарим тебе 3 дня Pro</div>
      <div className="text-white/50 text-sm mt-3 leading-relaxed max-w-[320px]">
        Безлимит AI-действий, встречи, цели по деньгам и еде — попробуй всё бесплатно 3 дня, без карты и обязательств.
      </div>
      <button
        disabled={claiming}
        onClick={() => {
          setClaiming(true);
          onAccept();
        }}
        className="w-full max-w-[320px] rounded-xl bg-white text-black text-sm font-medium py-3 mt-8 disabled:opacity-60"
      >
        {claiming ? "…" : "Принять подарок"}
      </button>
      <button onClick={onSkip} className="text-white/40 text-sm mt-4">
        Может позже
      </button>
    </div>
  );
}

function LastDayModal({ onExtend, onDismiss }: { onExtend: () => void; onDismiss: () => void }) {
  return (
    <div className="fixed inset-0 z-50 ark-gradient-bg flex flex-col items-center justify-center max-w-[480px] mx-auto px-6 text-center">
      <div className="text-5xl mb-5">⏰</div>
      <div className="text-2xl font-semibold">Последний день подписки</div>
      <div className="text-white/50 text-sm mt-3 leading-relaxed max-w-[320px]">
        Завтра тариф вернётся на Free. Продли сейчас, чтобы не потерять Pro-функции.
      </div>
      <button
        onClick={onExtend}
        className="w-full max-w-[320px] rounded-xl bg-white text-black text-sm font-medium py-3 mt-8"
      >
        Продлить подписку
      </button>
      <button onClick={onDismiss} className="text-white/40 text-sm mt-4">
        Напомнить позже
      </button>
    </div>
  );
}

function SubscriptionEndedModal({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="fixed inset-0 z-50 ark-gradient-bg flex flex-col items-center overflow-y-auto max-w-[480px] mx-auto px-6 py-10 text-center">
      <div className="flex-1 flex flex-col items-center justify-center min-h-[40vh]">
        <div className="text-5xl mb-5">⏳</div>
        <div className="text-2xl font-semibold">Подписка закончилась</div>
        <div className="text-white/50 text-sm mt-3 leading-relaxed max-w-[320px]">
          Pro-функции приостановлены. Продли подписку — или продолжай пользоваться бесплатным тарифом.
        </div>
      </div>
      <div className="w-full max-w-[340px]">
        <TariffPurchase />
      </div>
      <button onClick={onDismiss} className="text-white/40 text-xs mt-6 underline underline-offset-2">
        Остаться на бесплатной
      </button>
    </div>
  );
}

function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const slide = ONBOARDING_SLIDES[step];
  const isLast = step === ONBOARDING_SLIDES.length - 1;

  return (
    <div className="fixed inset-0 z-50 ark-gradient-bg flex flex-col max-w-[480px] mx-auto">
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2">
          <ArkMark size={28} />
          <span className="font-semibold tracking-wide text-sm">ARK PLANNER</span>
        </div>
        <button onClick={onDone} className="text-white/40 text-sm">
          Пропустить
        </button>
      </div>
      <div className="flex-1 flex flex-col px-6 pt-10">
        <div className="text-white/15 text-6xl font-bold">{slide.num}</div>
        <div className="text-2xl font-semibold mt-6">{slide.title}</div>
        <div className="text-white/50 text-sm mt-4 leading-relaxed">{slide.text}</div>
      </div>
      <div className="px-6 pb-8">
        <div className="flex gap-1.5 mb-4">
          {ONBOARDING_SLIDES.map((_, i) => (
            <div key={i} className={`h-1 flex-1 rounded-full ${i === step ? "bg-white" : "bg-white/15"}`} />
          ))}
        </div>
        <button
          onClick={() => (isLast ? onDone() : setStep((s) => s + 1))}
          className="w-full rounded-xl bg-white text-black text-sm font-medium py-3"
        >
          {isLast ? "Начать" : "Далее"}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try {
      return !localStorage.getItem(ONBOARDING_KEY);
    } catch {
      return false;
    }
  });

  const [trialToast, setTrialToast] = useState<string | null>(null);
  const [showTrialOffer, setShowTrialOffer] = useState(false);

  function finishOnboarding() {
    try {
      localStorage.setItem(ONBOARDING_KEY, "1");
    } catch {
      // ignore — worst case the onboarding shows again next time
    }
    setShowOnboarding(false);
    // Opening the app and clicking through onboarding is the "did something,
    // not just /start" signal that earns the one-time trial offer — but the
    // grant itself only happens once the person taps "Принять подарок".
    setShowTrialOffer(true);
  }

  function acceptTrial() {
    claimTrial().then((granted) => {
      setShowTrialOffer(false);
      if (granted) {
        setTrialToast("🎁 Тебе начислено 3 дня Pro — пробуй все функции!");
        setRefreshTick((t) => t + 1);
        setTimeout(() => setTrialToast(null), 6000);
      }
    });
  }

  const [tab, setTab] = useState<TabId>("digest");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [subStatus, setSubStatus] = useState<SubscriptionStatus | null>(null);
  const [dismissedEnded, setDismissedEnded] = useState(false);
  const [dismissedLastDay, setDismissedLastDay] = useState(false);
  const activeIndex = TABS.findIndex((t) => t.id === tab);
  const gated = !!subStatus?.required && !subStatus.subscribed;

  const tier = digest?.user.tier ?? "free";
  const showEnded = tier === "free" && !!digest?.user.had_subscription && !dismissedEnded;
  const hoursLeft = digest?.user.tier_expires_at
    ? (new Date(digest.user.tier_expires_at).getTime() - Date.now()) / 3_600_000
    : null;
  const showLastDay =
    tier !== "free" && hoursLeft !== null && hoursLeft > 0 && hoursLeft <= 24 && !dismissedLastDay;

  useEffect(() => {
    getDigest().then(setDigest).catch(() => setDigest(null));
  }, [refreshTick]);

  useEffect(() => {
    getSubscriptionStatus()
      .then(setSubStatus)
      .catch(() => setSubStatus({ required: false, subscribed: true, channel_url: null }));
  }, [refreshTick]);

  // Telegram keeps the Mini App's WebView alive in the background, so reopening
  // it can show whatever was on screen minutes or hours ago. Refetch whenever
  // it becomes visible again instead of leaving stale data on screen.
  useEffect(() => {
    function handleVisibility() {
      if (document.visibilityState === "visible") {
        setRefreshTick((t) => t + 1);
      }
    }
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  function handleSubmitted() {
    setRefreshTick((t) => t + 1);
  }

  return (
    <div className="min-h-screen max-w-[480px] mx-auto flex flex-col relative">
      {showOnboarding && <Onboarding onDone={finishOnboarding} />}
      {!showOnboarding && gated && (
        <SubscriptionGate
          channelUrl={subStatus!.channel_url}
          onVerified={() => setSubStatus((s) => (s ? { ...s, subscribed: true } : s))}
        />
      )}
      {!showOnboarding && !gated && showTrialOffer && (
        <TrialOffer onAccept={acceptTrial} onSkip={() => setShowTrialOffer(false)} />
      )}
      {!showOnboarding && !gated && !showTrialOffer && showEnded && (
        <SubscriptionEndedModal onDismiss={() => setDismissedEnded(true)} />
      )}
      {!showOnboarding && !gated && !showTrialOffer && !showEnded && showLastDay && (
        <LastDayModal
          onExtend={() => {
            setDismissedLastDay(true);
            setTab("settings");
          }}
          onDismiss={() => setDismissedLastDay(true)}
        />
      )}
      {trialToast && (
        <div className="fixed top-3 left-1/2 -translate-x-1/2 z-40 max-w-[90%] rounded-xl border border-white/15 bg-[#16161a]/95 backdrop-blur px-4 py-2.5 text-sm text-center shadow-lg">
          {trialToast}
        </div>
      )}
      <header className="flex items-center justify-between px-4 py-4 border-b border-white/10">
        <div className="flex items-center gap-2">
          <ArkMark />
          <span className="font-semibold tracking-wide">ARK PLANNER</span>
        </div>
        <span className="text-[11px] text-white/40 border border-white/15 rounded-full px-2 py-1">
          {digest ? TIER_LABELS[digest.user.tier] : "…"}
        </span>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-4 pb-44">
        {tab === "digest" && <DigestView digest={digest} onNavigate={setTab} />}
        {tab === "tasks" && <TasksView refreshTick={refreshTick} onChanged={handleSubmitted} />}
        {tab === "notes" && (
          <ListView<Note>
            key={refreshTick}
            section="notes"
            emptyLabel="Заметок пока нет"
            emptyHint="Идея, мысль, что угодно — текстом или голосом"
            render={(n) => ({ title: n.content })}
          />
        )}
        {tab === "money" && <MoneyView refreshTick={refreshTick} />}
        {tab === "meetings" && <MeetingsView refreshTick={refreshTick} onChanged={handleSubmitted} />}
        {tab === "food" && <FoodView refreshTick={refreshTick} />}
        {tab === "rituals" && <HabitsView refreshTick={refreshTick} onChanged={handleSubmitted} />}
        {tab === "settings" && (
          <SettingsView
            digest={digest}
            onTimeSaved={(field, value) =>
              setDigest((prev) =>
                prev ? { ...prev, user: { ...prev.user, [field]: value } } : prev
              )
            }
            onTzSaved={(tz) =>
              setDigest((prev) =>
                prev ? { ...prev, user: { ...prev.user, tz_offset: tz } } : prev
              )
            }
          />
        )}
      </main>

      <div className="fixed bottom-0 left-0 right-0 bg-[#0b0b0d]">
        <div className="pt-3 pb-2">
          <ComposerBar onSubmitted={handleSubmitted} />
        </div>
        <nav className="border-t border-white/10">
          <div className="mx-auto max-w-[480px] grid grid-cols-4 text-center">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`py-2 flex flex-col items-center gap-0.5 ${
                  i === activeIndex ? "text-white" : "text-white/35"
                }`}
              >
                <span className="text-[10px] font-mono">{t.num}</span>
                <span className="text-[11px]">{t.label}</span>
              </button>
            ))}
          </div>
        </nav>
      </div>
    </div>
  );
}
