import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "宝宝爱睡觉 · 你的主动式睡眠搭子",
  description: "睡前布置、睡中守护、醒后复盘的主动式睡眠搭子。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
