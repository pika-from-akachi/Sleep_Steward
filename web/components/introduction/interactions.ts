import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { getHeroFrame, type HeroFrame } from "./hero-progress";

function applyHeroFrame(root: HTMLElement, frame: HeroFrame) {
  root.dataset.copy = frame.copyState;
  root.style.setProperty("--room-scale", String(frame.roomScale));
  root.style.setProperty("--room-opacity", String(frame.roomOpacity));
  root.style.setProperty("--sky-scale", String(frame.skyScale));
  root.style.setProperty("--copy-opacity", String(frame.copyOpacity));
}

function mountNavigation(root: HTMLElement, header: HTMLElement): () => void {
  const button = header.querySelector<HTMLButtonElement>("[data-menu-toggle]");
  const menu = header.querySelector<HTMLElement>("[data-menu]");
  const links = [...header.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')];
  const themedSections = [...root.querySelectorAll<HTMLElement>("[data-nav-theme]")];

  const close = () => {
    if (!button || !menu || window.innerWidth >= 768) return;
    button.setAttribute("aria-expanded", "false");
    menu.hidden = true;
  };
  const toggle = () => {
    if (!button || !menu) return;
    const open = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(open));
    menu.hidden = !open;
  };
  const syncMenu = () => {
    if (!button || !menu) return;
    if (window.innerWidth >= 768) {
      menu.hidden = false;
      button.setAttribute("aria-expanded", "false");
    } else if (button.getAttribute("aria-expanded") !== "true") {
      menu.hidden = true;
    }
  };
  const updateTheme = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 24);
    const headerLine = Math.max(1, header.offsetHeight / 2);
    const current = themedSections.find((section) => {
      const rect = section.getBoundingClientRect();
      return rect.top <= headerLine && rect.bottom > headerLine;
    });
    header.classList.toggle("theme-light", current?.dataset.navTheme === "light");
  };

  button?.addEventListener("click", toggle);
  links.forEach((link) => link.addEventListener("click", close));
  window.addEventListener("scroll", updateTheme, { passive: true });
  window.addEventListener("resize", syncMenu, { passive: true });
  syncMenu();
  updateTheme();

  return () => {
    button?.removeEventListener("click", toggle);
    links.forEach((link) => link.removeEventListener("click", close));
    window.removeEventListener("scroll", updateTheme);
    window.removeEventListener("resize", syncMenu);
  };
}

function mountHeroScene(hero: HTMLElement, reducedMotion: boolean): () => void {
  if (!hero.querySelector("[data-hero-room]")) return () => undefined;

  applyHeroFrame(hero, getHeroFrame(0, reducedMotion));
  const trigger = ScrollTrigger.create({
    trigger: hero,
    start: "top top",
    end: "bottom bottom",
    scrub: true,
    onUpdate(self) {
      applyHeroFrame(hero, getHeroFrame(self.progress, reducedMotion));
    },
  });

  return () => trigger.kill();
}

function mountSectionReveals(root: HTMLElement, reducedMotion: boolean): () => void {
  if (reducedMotion) return () => undefined;

  const triggers: ScrollTrigger[] = [];

  root.querySelectorAll<HTMLElement>("[data-reveal]").forEach((element) => {
    const tween = gsap.from(element, {
      y: 48,
      opacity: 0,
      duration: 1.1,
      ease: "power3.out",
      paused: true,
    });
    triggers.push(
      ScrollTrigger.create({
        trigger: element,
        start: "top 84%",
        once: true,
        onEnter: () => tween.play(),
      }),
    );
  });

  root.querySelectorAll<HTMLElement>("[data-highlight-text]").forEach((line) => {
    const tween = gsap.fromTo(
      line,
      { opacity: 0.24 },
      { opacity: 1, ease: "none", paused: true },
    );
    triggers.push(
      ScrollTrigger.create({
        trigger: line,
        start: "top 78%",
        end: "bottom 62%",
        scrub: true,
        animation: tween,
      }),
    );
  });

  root.querySelectorAll<HTMLElement>("[data-loop-step]").forEach((step) => {
    const index = step.dataset.loopStep ?? "0";
    triggers.push(
      ScrollTrigger.create({
        trigger: step,
        start: "top center",
        end: "bottom center",
        onToggle: ({ isActive }) => {
          step.classList.toggle("is-active", isActive);
          root
            .querySelector(`[data-loop-node="${index}"]`)
            ?.classList.toggle("is-active", isActive);
        },
      }),
    );
  });

  root.querySelectorAll<HTMLElement>("[data-ecosystem-node]").forEach((node, index) => {
    const tween = gsap.from(node, {
      scale: 0.72,
      opacity: 0,
      duration: 0.8,
      delay: index * 0.06,
      paused: true,
    });
    triggers.push(
      ScrollTrigger.create({
        trigger: node,
        start: "top 88%",
        once: true,
        onEnter: () => tween.play(),
      }),
    );
  });

  return () => triggers.forEach((trigger) => trigger.kill());
}

export function mountIntroduction(root: HTMLElement): () => void {
  gsap.registerPlugin(ScrollTrigger);

  const cleanups: Array<() => void> = [];
  const header = root.querySelector<HTMLElement>("[data-header]");
  const hero = root.querySelector<HTMLElement>("[data-hero]");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (header) cleanups.push(mountNavigation(root, header));
  if (hero) cleanups.push(mountHeroScene(hero, reducedMotion));
  cleanups.push(mountSectionReveals(root, reducedMotion));

  let lenis: Lenis | undefined;
  let rafId = 0;

  if (window.innerWidth >= 992 && !reducedMotion) {
    lenis = new Lenis({ duration: 1.2, smoothWheel: true });
    const raf = (time: number) => {
      lenis?.raf(time);
      rafId = requestAnimationFrame(raf);
    };
    rafId = requestAnimationFrame(raf);
  }

  return () => {
    cleanups.forEach((cleanup) => cleanup());
    lenis?.destroy();
    cancelAnimationFrame(rafId);
  };
}
