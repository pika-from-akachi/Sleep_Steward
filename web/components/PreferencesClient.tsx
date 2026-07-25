"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Droplets,
  Lightbulb,
  Pencil,
  Plus,
  Thermometer,
  Trash2,
  X,
} from "lucide-react";
import NightSky from "@/components/NightSky";
import TopNav from "@/components/TopNav";

interface PrefItem {
  id: string;
  name: string;
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number;
  lightColorTemp: "warm" | "cool";
  isDefault: boolean;
}

type PrefDraft = Omit<PrefItem, "id" | "isDefault">;

const EMPTY_DRAFT: PrefDraft = {
  name: "",
  tempMin: 22,
  tempMax: 25,
  humidityMin: 40,
  humidityMax: 60,
  lightBrightness: 15,
  lightColorTemp: "warm",
};

function draftFrom(pref: PrefItem): PrefDraft {
  return {
    name: pref.name,
    tempMin: pref.tempMin,
    tempMax: pref.tempMax,
    humidityMin: pref.humidityMin,
    humidityMax: pref.humidityMax,
    lightBrightness: pref.lightBrightness,
    lightColorTemp: pref.lightColorTemp,
  };
}

export default function PreferencesClient({
  nickname,
  initialPrefs,
}: {
  nickname: string;
  initialPrefs: PrefItem[];
}) {
  const [prefs, setPrefs] = useState(initialPrefs);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PrefDraft>(EMPTY_DRAFT);
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  function openCreate() {
    setEditingId(null);
    setDraft({ ...EMPTY_DRAFT });
    setError("");
    setEditorOpen(true);
  }

  function openEdit(pref: PrefItem) {
    setEditingId(pref.id);
    setDraft(draftFrom(pref));
    setError("");
    setEditorOpen(true);
  }

  function closeEditor() {
    if (saving) return;
    setEditorOpen(false);
    setError("");
  }

  function validateDraft() {
    if (!draft.name.trim()) return "请给这套方案起个名字";
    if (draft.tempMin >= draft.tempMax) return "最低温度需要小于最高温度";
    if (draft.humidityMin >= draft.humidityMax) return "最低湿度需要小于最高湿度";
    if (draft.tempMin < 12 || draft.tempMax > 35) return "温度范围需要在 12–35℃ 之间";
    if (draft.humidityMin < 20 || draft.humidityMax > 90) return "湿度范围需要在 20–90% 之间";
    if (draft.lightBrightness < 0 || draft.lightBrightness > 100) return "灯光亮度需要在 0–100% 之间";
    return "";
  }

  async function save() {
    const validationError = validateDraft();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setError("");
    const res = await fetch("/api/prefs", {
      method: editingId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editingId ? { id: editingId, ...draft } : draft),
    });
    const data = await res.json().catch(() => ({}));
    setSaving(false);

    if (!res.ok) {
      setError(data.error || "保存失败，请再试一次");
      return;
    }

    const saved = data.pref as PrefItem;
    setPrefs((current) =>
      editingId
        ? current.map((pref) => (pref.id === saved.id ? saved : pref))
        : [...current, saved],
    );
    setEditorOpen(false);
    setToast(editingId ? "睡眠方案已更新" : "新的睡眠方案已加入");
    window.setTimeout(() => setToast(""), 3600);
  }

  async function remove(pref: PrefItem) {
    if (pref.isDefault) return;
    if (!window.confirm(`确认删除「${pref.name}」吗？此操作无法撤销。`)) return;

    const res = await fetch(`/api/prefs?id=${encodeURIComponent(pref.id)}`, {
      method: "DELETE",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setToast(data.error || "删除失败，请再试一次");
      window.setTimeout(() => setToast(""), 4200);
      return;
    }
    setPrefs((current) => current.filter((item) => item.id !== pref.id));
    setToast("睡眠方案已删除");
    window.setTimeout(() => setToast(""), 3600);
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden px-5">
      <NightSky blur={12} />
      <TopNav />

      <div className="relative z-10 mx-auto mb-24 mt-28 w-full max-w-3xl px-2 py-10 md:mt-32 md:px-4">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="mt-6 flex flex-col gap-7 sm:flex-row sm:items-end sm:justify-between"
        >
          <div>
            <p className="text-[11px] tracking-[0.3em] text-cream-dim">我的偏好 · {nickname}</p>
            <h1 className="serif mt-3 text-[36px] font-semibold tracking-[0.04em] md:text-[42px]">
              把舒服，留给每一晚。
            </h1>
            <p className="mt-2 text-[13px] leading-6 text-cream-dim">
              保存不同季节与场景的温度、湿度和灯光习惯。
            </p>
          </div>
          <button
            type="button"
            onClick={openCreate}
            className="btn-moon flex shrink-0 items-center justify-center gap-2 rounded-full px-5 py-3 text-[12.5px] font-semibold tracking-[0.12em]"
          >
            <Plus size={16} strokeWidth={1.8} />
            新建方案
          </button>
        </motion.div>

        <section className="mt-10 space-y-4">
          {prefs.map((pref, index) => (
            <motion.article
              key={pref.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(index * 0.06, 0.24) }}
              className="glass rounded-[26px] p-5 md:p-6"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h2 className="serif text-[22px] tracking-[0.05em]">{pref.name}</h2>
                    {pref.isDefault && (
                      <span className="rounded-full border border-moon/25 bg-moon/10 px-2.5 py-1 text-[9.5px] tracking-[0.16em] text-moon">
                        默认方案
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] text-cream-dim">
                    {pref.isDefault ? "一键进入时优先使用" : "可在仪表盘点选使用"}
                  </p>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => openEdit(pref)}
                    aria-label={`编辑${pref.name}`}
                    className="rounded-full border border-hair p-2.5 text-cream-dim transition-colors hover:border-moon/40 hover:text-cream"
                  >
                    <Pencil size={14} strokeWidth={1.5} />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(pref)}
                    disabled={pref.isDefault}
                    aria-label={pref.isDefault ? "默认方案不可删除" : `删除${pref.name}`}
                    title={pref.isDefault ? "默认方案不可删除" : "删除方案"}
                    className="rounded-full border border-hair p-2.5 text-cream-dim transition-colors hover:border-[#e8a598]/40 hover:text-[#e8a598] disabled:cursor-not-allowed disabled:opacity-25"
                  >
                    <Trash2 size={14} strokeWidth={1.5} />
                  </button>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-3 divide-x divide-hair border-y border-hair py-4">
                <Metric
                  icon={<Thermometer size={14} strokeWidth={1.4} />}
                  label="温度"
                  value={`${pref.tempMin}–${pref.tempMax}℃`}
                />
                <Metric
                  icon={<Droplets size={14} strokeWidth={1.4} />}
                  label="湿度"
                  value={`${pref.humidityMin}–${pref.humidityMax}%`}
                />
                <Metric
                  icon={<Lightbulb size={14} strokeWidth={1.4} />}
                  label={pref.lightColorTemp === "warm" ? "暖光" : "冷光"}
                  value={`${pref.lightBrightness}%`}
                />
              </div>
            </motion.article>
          ))}
        </section>
      </div>

      <AnimatePresence>
        {editorOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 flex items-end justify-center bg-night-0/70 px-4 backdrop-blur-sm sm:items-center"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeEditor();
            }}
          >
            <motion.section
              initial={{ opacity: 0, y: 28, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20 }}
              className="glass max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-t-[28px] p-6 sm:rounded-[28px] sm:p-8"
              role="dialog"
              aria-modal="true"
              aria-labelledby="pref-editor-title"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] tracking-[0.26em] text-cream-dim">
                    {editingId ? "调整睡眠方案" : "收下一份新的偏好"}
                  </p>
                  <h2 id="pref-editor-title" className="serif mt-2 text-[26px]">
                    {editingId ? "编辑方案" : "新建方案"}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={closeEditor}
                  aria-label="关闭"
                  className="rounded-full border border-hair p-2 text-cream-dim hover:text-cream"
                >
                  <X size={16} strokeWidth={1.5} />
                </button>
              </div>

              <label className="mt-7 block text-[11px] tracking-[0.16em] text-cream-dim">
                方案名称
                <input
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  maxLength={24}
                  placeholder="例如：盛夏微凉"
                  className="mt-2 w-full rounded-2xl border border-hair bg-white/[0.03] px-4 py-3.5 text-[13px] text-cream outline-none placeholder:text-cream-dim/55 focus:border-moon/45"
                />
              </label>

              <div className="mt-6 grid grid-cols-2 gap-3">
                <NumberField label="最低温度" unit="℃" value={draft.tempMin} min={12} max={34}
                  onChange={(value) => setDraft((current) => ({ ...current, tempMin: value }))} />
                <NumberField label="最高温度" unit="℃" value={draft.tempMax} min={13} max={35}
                  onChange={(value) => setDraft((current) => ({ ...current, tempMax: value }))} />
                <NumberField label="最低湿度" unit="%" value={draft.humidityMin} min={20} max={89}
                  onChange={(value) => setDraft((current) => ({ ...current, humidityMin: value }))} />
                <NumberField label="最高湿度" unit="%" value={draft.humidityMax} min={21} max={90}
                  onChange={(value) => setDraft((current) => ({ ...current, humidityMax: value }))} />
              </div>

              <div className="mt-6">
                <div className="mb-2 flex items-center justify-between text-[11px] text-cream-dim">
                  <span className="tracking-[0.16em]">灯光亮度</span>
                  <span className="serif text-[18px] text-cream">{draft.lightBrightness}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={draft.lightBrightness}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      lightBrightness: Number(event.target.value),
                    }))
                  }
                  className="w-full accent-[#eed9a4]"
                />
              </div>

              <div className="mt-6">
                <p className="mb-2 text-[11px] tracking-[0.16em] text-cream-dim">灯光色温</p>
                <div className="grid grid-cols-2 overflow-hidden rounded-2xl border border-hair">
                  {(["warm", "cool"] as const).map((colorTemp) => (
                    <button
                      key={colorTemp}
                      type="button"
                      onClick={() =>
                        setDraft((current) => ({ ...current, lightColorTemp: colorTemp }))
                      }
                      className={`py-3 text-[12px] transition-colors ${
                        draft.lightColorTemp === colorTemp
                          ? "bg-moon/15 text-moon"
                          : "text-cream-dim hover:text-cream"
                      }`}
                    >
                      {colorTemp === "warm" ? "暖光" : "冷光"}
                    </button>
                  ))}
                </div>
              </div>

              {error && <p className="mt-5 text-[12px] text-[#e8a598]">{error}</p>}

              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="btn-moon mt-7 w-full rounded-2xl py-4 text-[13px] font-semibold tracking-[0.28em] disabled:opacity-60"
              >
                {saving ? "正在保存" : editingId ? "保存修改" : "加入我的方案"}
              </button>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            aria-live="polite"
            className="glass fixed left-1/2 top-24 z-50 -translate-x-1/2 rounded-full px-5 py-3 text-[12px] text-cream"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="px-2 text-center">
      <div className="flex items-center justify-center gap-1.5 text-[10px] tracking-[0.14em] text-cream-dim">
        {icon}
        {label}
      </div>
      <p className="serif mt-1.5 text-[18px]">{value}</p>
    </div>
  );
}

function NumberField({
  label,
  unit,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-[10.5px] tracking-[0.12em] text-cream-dim">
      {label}
      <div className="mt-2 flex items-center rounded-2xl border border-hair bg-white/[0.03] px-3 focus-within:border-moon/45">
        <input
          type="number"
          min={min}
          max={max}
          step={1}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="min-w-0 flex-1 bg-transparent py-3 text-[13px] text-cream outline-none"
        />
        <span className="text-[11px] text-cream-dim">{unit}</span>
      </div>
    </label>
  );
}
