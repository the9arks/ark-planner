import { useEffect, useState } from "react";
import { getDigest, getSection, type Digest } from "./api";

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
  { id: "rituals", num: "07", label: "Ритуалы" },
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
}: {
  title: string;
  hint?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 flex flex-col gap-2 min-h-[110px]">
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

function CountCard({ title, count, hint }: { title: string; count: number; hint: string }) {
  return (
    <Card title={title}>
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

function DigestView({ digest }: { digest: Digest | null }) {
  const today = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const d = digest?.digest;
  const hasAny =
    !!d &&
    (d.tasks_today || d.notes_today || d.meetings_today || d.money_today || d.food_today);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl bg-gradient-to-br from-white/[0.06] to-white/[0.01] border border-white/10 p-5">
        <div className="text-white/40 text-sm capitalize">{today}</div>
        <div className="text-2xl font-semibold mt-1">Доброе утро</div>
        <div className="text-white/50 text-sm mt-2">
          {hasAny
            ? "Вот что уже записано сегодня."
            : "Записей пока нет — надиктуй или напиши, что происходит."}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <CountCard title="Задачи" count={d?.tasks_today ?? 0} hint="Добавить первую" />
        <CountCard title="Заметки" count={d?.notes_today ?? 0} hint="Мысль или запись" />
        <CountCard title="Встречи" count={d?.meetings_today ?? 0} hint="Запланировать" />
        <CountCard title="Еда" count={d?.food_today ?? 0} hint="Сфоткай еду" />
      </div>

      <CountCard title="Деньги" count={d?.money_today ?? 0} hint="Настрой бюджет" />
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

function ComposerBar() {
  return (
    <div className="fixed bottom-[76px] left-0 right-0 px-4">
      <div className="mx-auto max-w-[420px] flex items-center gap-2 rounded-full border border-white/10 bg-[#0f0f12]/95 backdrop-blur px-4 py-3">
        <input
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-white/30"
          placeholder="Скажи или напиши что-нибудь…"
        />
        <button className="w-8 h-8 rounded-full bg-white text-black text-sm grid place-items-center">
          →
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
interface RitualLog { id: string; created_at: string }

export default function App() {
  const [tab, setTab] = useState<TabId>("digest");
  const [digest, setDigest] = useState<Digest | null>(null);
  const activeIndex = TABS.findIndex((t) => t.id === tab);

  useEffect(() => {
    getDigest().then(setDigest).catch(() => setDigest(null));
  }, []);

  return (
    <div className="min-h-screen max-w-[480px] mx-auto flex flex-col relative">
      <header className="flex items-center justify-between px-4 py-4 border-b border-white/10">
        <div className="flex items-center gap-2">
          <ArkMark />
          <span className="font-semibold tracking-wide">ARK PLANNER</span>
        </div>
        <span className="text-[11px] text-white/40 border border-white/15 rounded-full px-2 py-1">
          {digest?.user.is_pro ? "Pro" : "Free"}
        </span>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-4 pb-56">
        {tab === "digest" && <DigestView digest={digest} />}
        {tab === "tasks" && (
          <ListView<Task>
            section="tasks"
            emptyLabel="Задач пока нет"
            emptyHint="Напиши боту: «купить молоко завтра»"
            render={(t) => ({ title: t.title, subtitle: formatWhen(t.due_at) })}
          />
        )}
        {tab === "notes" && (
          <ListView<Note>
            section="notes"
            emptyLabel="Заметок пока нет"
            emptyHint="Скинь мысль текстом или голосом"
            render={(n) => ({ title: n.content })}
          />
        )}
        {tab === "money" && (
          <ListView<MoneyEntry>
            section="money"
            emptyLabel="Трат пока нет"
            emptyHint="Пришли фото чека — занесу автоматически"
            render={(m) => ({
              title: `${m.amount}₽ ${m.category ?? ""}`,
              subtitle: m.comment ?? undefined,
            })}
          />
        )}
        {tab === "meetings" && (
          <ListView<Meeting>
            section="meetings"
            emptyLabel="Встреч пока нет"
            emptyHint="Напиши: «завтра в 15:00 встреча с Андреем»"
            render={(m) => ({
              title: m.with_who ? `Встреча с ${m.with_who}` : m.title,
              subtitle: formatWhen(m.starts_at),
            })}
          />
        )}
        {tab === "food" && (
          <ListView<FoodEntry>
            section="food"
            emptyLabel="Приёмов пищи пока нет"
            emptyHint="Сфоткай тарелку — посчитаю калории и БЖУ"
            render={(f) => ({
              title: f.description ?? "Приём пищи",
              subtitle: f.calories ? `~${f.calories} ккал` : undefined,
            })}
          />
        )}
        {tab === "rituals" && (
          <ListView<RitualLog>
            section="rituals"
            emptyLabel="Ритуалов пока нет"
            emptyHint="Например: «сон 6.5 часов» каждый день"
            render={(r) => ({ title: formatWhen(r.created_at) || "Отметка" })}
          />
        )}
        {tab === "settings" && (
          <EmptyView label="Настройки" hint="Профиль, цели по калориям, тариф Pro" />
        )}
      </main>

      <ComposerBar />

      <nav className="fixed bottom-0 left-0 right-0 border-t border-white/10 bg-[#0b0b0d]/95 backdrop-blur">
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
  );
}
