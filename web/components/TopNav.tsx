"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, House, SlidersHorizontal } from "lucide-react";
import SleepAudio from "@/components/SleepAudio";

/**
 * 功能页统一顶部导航:悬浮居中的胶囊长条,圆形图标按钮,当前板块圆底高亮。
 * 仪表盘 / 睡眠记录 / 我的偏好;报告页归属「睡眠记录」高亮。
 * 右侧独立圆形为助眠声音入口(音乐图标,下拉选曲)。
 * 关键尺寸用内联样式锁定,避免原子类缺失导致比例失常。
 */
const ITEMS = [
  { href: "/dashboard", label: "仪表盘", Icon: House },
  { href: "/history", label: "睡眠记录", Icon: CalendarDays },
  { href: "/preferences", label: "我的偏好", Icon: SlidersHorizontal },
];

const BTN = 52;
const shellStyle: React.CSSProperties = {
  borderRadius: 999,
  border: "1px solid var(--hair)",
  background: "rgba(14, 15, 36, 0.55)",
  boxShadow: "0 10px 40px rgba(0,0,0,0.35)",
  backdropFilter: "blur(20px)",
  WebkitBackdropFilter: "blur(20px)",
};

export default function TopNav({ userType = "adult" }: { userType?: "adult" | "child" }) {
  const pathname = usePathname();
  const activeHref = pathname.startsWith("/report") ? "/history" : pathname;

  return (
    <nav
      style={{
        position: "fixed",
        top: 20,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 40,
        display: "flex",
        alignItems: "center",
        gap: 14,
      }}
    >
      <div style={{ ...shellStyle, display: "flex", alignItems: "center", gap: 8, padding: 8 }}>
        {ITEMS.map(({ href, label, Icon }) => {
          const active = activeHref === href || activeHref.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              title={label}
              aria-current={active ? "page" : undefined}
              className={active ? "text-moon" : "text-cream-dim hover:text-cream"}
              style={{
                width: BTN,
                height: BTN,
                display: "grid",
                placeItems: "center",
                borderRadius: "50%",
                background: active ? "rgba(255,255,255,0.10)" : "transparent",
                transition: "color 0.2s, background 0.2s",
              }}
            >
              <Icon size={23} strokeWidth={1.5} />
            </Link>
          );
        })}
      </div>
      <SleepAudio userType={userType} />
    </nav>
  );
}
