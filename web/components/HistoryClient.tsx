"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { zhCN } from "date-fns/locale";
import {
  ChevronLeft,
  ChevronRight,
  Clock3,
  Mic2,
  MoonStar,
} from "lucide-react";
import NightSky from "@/components/NightSky";
import TopNav from "@/components/TopNav";

interface HistorySession {
  id: string;
  profileName: string;
  startedAt: string;
  endedAt: string;
  durationMin: number;
}

interface CommandRecord {
  id: string;
  rawText: string;
  mode: string;
  parsedJson: string;
  matchedDevice: string | null;
  createdAt: string;
}

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function durationLabel(minutes: number) {
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`;
}

function commandTranslation(command: CommandRecord) {
  try {
    const parsed = JSON.parse(command.parsedJson) as {
      action?: string;
      status?: string;
      params?: { brightness?: number; targetTempC?: number; deltaC?: number; trackId?: string };
    };
    if (parsed.status === "unparsed") return "未执行 · 已使用安全降级";
    if (parsed.action === "setLight") {
      const brightness = parsed.params?.brightness;
      return brightness === 0 ? "关闭灯光" : `调整灯光至 ${brightness ?? "--"}%`;
    }
    if (parsed.action === "setClimate") {
      if (typeof parsed.params?.targetTempC === "number") {
        return `设置温度为 ${parsed.params.targetTempC}℃`;
      }
      return parsed.params?.deltaC && parsed.params.deltaC > 0 ? "调高温度" : "调低温度";
    }
    if (parsed.action === "playAudio") return `播放 ${parsed.params?.trackId ?? "助眠声音"}`;
    if (parsed.action === "stopAudio") return "停止助眠声音";
  } catch {}
  return command.matchedDevice ? `已调度 ${command.matchedDevice}` : "保留原始翻译记录";
}

export default function HistoryClient({
  nickname,
  sessions,
  commands,
}: {
  nickname: string;
  sessions: HistorySession[];
  commands: CommandRecord[];
}) {
  const initialMonth = sessions[0] ? new Date(sessions[0].startedAt) : new Date();
  const [month, setMonth] = useState(startOfMonth(initialMonth));

  const calendarDays = useMemo(
    () =>
      eachDayOfInterval({
        start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }),
        end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }),
      }),
    [month],
  );

  const sessionsByDay = useMemo(() => {
    const grouped = new Map<string, HistorySession[]>();
    for (const session of sessions) {
      const key = format(new Date(session.startedAt), "yyyy-MM-dd");
      grouped.set(key, [...(grouped.get(key) ?? []), session]);
    }
    return grouped;
  }, [sessions]);

  const visibleSessions = useMemo(
    () =>
      sessions.filter((session) =>
        isSameMonth(new Date(session.startedAt), month),
      ),
    [month, sessions],
  );

  return (
    <main className="relative min-h-screen overflow-x-hidden px-5">
      <NightSky blur={12} />
      <TopNav />

      <div className="relative z-10 mx-auto mb-24 mt-28 w-full max-w-4xl px-2 py-10 md:mt-32 md:px-4">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        >
          <p className="mt-6 text-[11px] tracking-[0.3em] text-cream-dim">睡眠记录 · {nickname}</p>
          <h1 className="serif mt-3 text-[36px] font-semibold tracking-[0.04em] md:text-[42px]">
            每一夜，都有迹可循。
          </h1>
          <p className="mt-2 text-[13px] leading-6 text-cream-dim">
            月历里的暖色日期已经留下睡眠记录，点开即可回到那一夜。
          </p>
        </motion.div>

        <section className="mt-10 grid gap-6 lg:grid-cols-[1.45fr_0.8fr]">
          <div className="glass rounded-[28px] p-5 md:p-7">
            <div className="mb-6 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setMonth((current) => subMonths(current, 1))}
                aria-label="上个月"
                className="rounded-full border border-hair p-2 text-cream-dim transition-colors hover:border-moon/40 hover:text-cream"
              >
                <ChevronLeft size={17} strokeWidth={1.5} />
              </button>
              <div className="text-center">
                <p className="serif text-[22px] tracking-[0.08em]">
                  {format(month, "yyyy年 M月", { locale: zhCN })}
                </p>
                <p className="mt-1 text-[10px] tracking-[0.24em] text-cream-dim">
                  {visibleSessions.length} 次睡眠
                </p>
              </div>
              <button
                type="button"
                onClick={() => setMonth((current) => addMonths(current, 1))}
                aria-label="下个月"
                className="rounded-full border border-hair p-2 text-cream-dim transition-colors hover:border-moon/40 hover:text-cream"
              >
                <ChevronRight size={17} strokeWidth={1.5} />
              </button>
            </div>

            <div className="grid grid-cols-7">
              {WEEKDAYS.map((weekday) => (
                <div
                  key={weekday}
                  className="pb-3 text-center text-[10px] tracking-[0.18em] text-cream-dim"
                >
                  {weekday}
                </div>
              ))}
              {calendarDays.map((day) => {
                const key = format(day, "yyyy-MM-dd");
                const daySessions = sessionsByDay.get(key) ?? [];
                const latest = daySessions[0];
                const inMonth = isSameMonth(day, month);
                const common =
                  "relative flex aspect-square items-center justify-center rounded-2xl text-[12px] transition-all";

                if (!latest) {
                  return (
                    <div
                      key={key}
                      className={`${common} ${inMonth ? "text-cream-dim" : "text-cream-dim/25"} ${
                        isToday(day) ? "ring-1 ring-inset ring-hair" : ""
                      }`}
                    >
                      {format(day, "d")}
                    </div>
                  );
                }

                return (
                  <Link
                    key={key}
                    href={`/report/${latest.id}`}
                    aria-label={`${format(day, "M月d日")}，${daySessions.length} 次睡眠，查看报告`}
                    className={`${common} group bg-moon/[0.13] text-moon ring-1 ring-inset ring-moon/25 hover:-translate-y-0.5 hover:bg-moon/20 ${
                      !inMonth ? "opacity-45" : ""
                    }`}
                  >
                    <span className="serif text-[15px]">{format(day, "d")}</span>
                    <span className="absolute bottom-1.5 h-1 w-1 rounded-full bg-moon shadow-[0_0_8px_rgba(245,223,174,.8)]" />
                    {daySessions.length > 1 && (
                      <span className="absolute right-1.5 top-1 text-[8px] text-moon/70">
                        {daySessions.length}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>

          <aside className="rounded-[28px] border border-hair bg-night-0/25 p-6">
            <div className="flex items-center gap-2 text-[11px] tracking-[0.24em] text-cream-dim">
              <MoonStar size={15} strokeWidth={1.4} />
              本月夜记
            </div>
            {visibleSessions.length === 0 ? (
              <p className="mt-8 text-[13px] leading-6 text-cream-dim">
                这个月还没有记录。睡眠结束后，它会安静地出现在月历里。
              </p>
            ) : (
              <div className="mt-4">
                {visibleSessions.map((session) => (
                  <Link
                    key={session.id}
                    href={`/report/${session.id}`}
                    className="block border-b border-dashed border-hair py-4 transition-colors hover:text-moon"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[13.5px]">{session.profileName}</p>
                        <p className="mt-1 text-[11px] text-cream-dim">
                          {format(new Date(session.startedAt), "M月d日 HH:mm")}
                        </p>
                      </div>
                      <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-cream-dim">
                        <Clock3 size={12} strokeWidth={1.5} />
                        {durationLabel(session.durationMin)}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </aside>
        </section>

        <section className="mt-12">
          <div className="flex items-end justify-between border-b border-hair pb-4">
            <div>
              <div className="flex items-center gap-2 text-[11px] tracking-[0.26em] text-cream-dim">
                <Mic2 size={14} strokeWidth={1.4} />
                语音指令翻译记录
              </div>
              <p className="mt-2 text-[12px] text-cream-dim">保留最近 50 条原话与系统理解结果</p>
            </div>
            <span className="serif text-[26px] text-moon">{commands.length}</span>
          </div>

          {commands.length === 0 ? (
            <p className="py-10 text-[13px] text-cream-dim">还没有语音指令记录。</p>
          ) : (
            <div>
              {commands.map((command) => (
                <article
                  key={command.id}
                  className="grid gap-2 border-b border-dashed border-hair py-5 sm:grid-cols-[1fr_auto] sm:items-center"
                >
                  <div>
                    <p className="text-[14px]">「{command.rawText}」</p>
                    <p className="mt-1.5 text-[12px] text-cream-dim">
                      {commandTranslation(command)}
                    </p>
                  </div>
                  <div className="text-left text-[10.5px] leading-5 tracking-[0.08em] text-cream-dim sm:text-right">
                    <p>{command.mode === "hardcoded" ? "快捷指令" : "AI 理解"}</p>
                    <p>{format(new Date(command.createdAt), "yyyy.MM.dd HH:mm")}</p>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
