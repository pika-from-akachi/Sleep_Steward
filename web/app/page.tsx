import type { Metadata, Viewport } from "next";
import IntroductionPage from "@/components/introduction/IntroductionPage";

export const metadata: Metadata = {
  title: "主动睡眠搭子｜Hack the Rest",
  description: "主动睡眠搭子能够发现睡眠中的需求，并主动提供照顾。",
};

export const viewport: Viewport = {
  themeColor: "#061a2f",
};

export default function HomePage() {
  return <IntroductionPage />;
}
