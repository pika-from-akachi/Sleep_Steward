"use client";

import { useEffect, useRef } from "react";
import { ArrowUpRight } from "lucide-react";
import Image from "next/image";

const INTRODUCTION_STYLES = [
  "/introduction/styles/tokens.css",
  "/introduction/styles/base.css",
  "/introduction/styles/hero.css",
  "/introduction/styles/sections.css",
  "/introduction/styles/responsive.css",
];

export default function IntroductionPage() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;

    void import("./interactions").then(({ mountIntroduction }) => {
      if (!cancelled && rootRef.current) {
        cleanup = mountIntroduction(rootRef.current);
      }
    });

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);

  return (
    <div ref={rootRef} className="introduction">
      {INTRODUCTION_STYLES.map((href) => (
        <link key={href} rel="stylesheet" href={href} />
      ))}

      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <div className="grain" aria-hidden="true" />

      <header className="site-header" data-header>
        <a className="brand" href="#hero" aria-label="主动睡眠搭子首页">
          <span className="brand__cn">主动睡眠搭子</span>
          <span className="brand__en">Hack the Rest</span>
        </a>
        <button
          className="menu-toggle"
          type="button"
          data-menu-toggle
          aria-expanded="false"
          aria-controls="site-menu"
        >
          <span>Menu</span>
          <i aria-hidden="true" />
        </button>
        <nav className="site-nav" id="site-menu" data-menu aria-label="主要导航">
          <a href="#care-loop">How it cares</a>
          <a href="#vision">Vision</a>
          <a className="nav-cta" href="/welcome">
            认识睡眠搭子
          </a>
        </nav>
      </header>

      <main id="main-content">
        <section className="hero" id="hero" data-hero data-copy="care" data-nav-theme="dark">
          <div className="hero__sticky">
            <Image
              className="hero__sky"
              data-hero-sky
              src="/media/night-sky.jpg"
              width="1447"
              height="1087"
              sizes="100vw"
              preload
              alt=""
              aria-hidden="true"
            />
            <Image
              className="hero__room"
              data-hero-room
              src="/media/room-transparent.webp"
              width="1448"
              height="1086"
              sizes="100vw"
              loading="eager"
              alt=""
              aria-hidden="true"
            />

            <div className="hero__veil" aria-hidden="true" />
            <div className="hero__copy" aria-live="polite">
              <p className="hero__eyebrow">主动睡眠搭子 · 01</p>
              <h1 className="hero__copy-item" data-copy="care">
                睡吧，
                <br />
                我来处理。
              </h1>
              <p className="hero__copy-item" data-copy="companion">
                你的第一个
                <br />
                主动式睡眠搭子。
              </p>
              <p className="hero__copy-item hero__copy-item--en" data-copy="rest">
                Hack
                <br />
                the Rest.
              </p>
            </div>
            <p className="hero__scroll-cue">
              <span>Scroll to enter</span>
              <i aria-hidden="true" />
            </p>
            <p className="hero__corner-note">SEE · VERIFY · ACT · RETURN</p>
          </div>
        </section>

        <noscript>
          <section className="noscript-message">
            <h1>睡吧，我来处理。</h1>
            <p>睡眠科技不应该只记录人的状态，它应该真正照顾人。</p>
          </section>
        </noscript>

        <div className="story-surface" aria-label="主动睡眠搭子品牌故事">
          <Image
            className="story-surface__backdrop"
            src="/media/long-night-backdrop.jpg"
            alt=""
            aria-hidden="true"
            width="941"
            height="1672"
          />

          <section className="manifesto" id="manifesto" data-nav-theme="dark">
            <div className="section-shell manifesto__layout">
              <div className="manifesto__index" data-reveal>
                <span>01</span>
                <p>WHY WE CARE</p>
              </div>
              <div className="manifesto__statement">
                <p className="eyebrow" data-reveal>
                  From monitoring to caring
                </p>
                <h2>
                  <span data-highlight-text>睡眠科技不应该</span>
                  <span data-highlight-text>只记录人的状态。</span>
                  <span data-highlight-text>它应该真正照顾人。</span>
                </h2>
              </div>
              <div className="manifesto__values">
                <article data-reveal>
                  <span>主动照顾</span>
                  <p>不是告诉你被子被踢开，而是在确认需要帮助后，真正把它盖好。</p>
                </article>
                <article data-reveal>
                  <span>安心陪伴</span>
                  <p>你不需要在睡眠中保持警觉，剩下的事情交给一个安静的伙伴。</p>
                </article>
                <article data-reveal>
                  <span>减少中断</span>
                  <p>让用户和照护者少一次夜间醒来、检查与调整，多一段完整睡眠。</p>
                </article>
              </div>
            </div>
          </section>

          <section className="care-loop" id="care-loop" data-nav-theme="dark">
            <div className="care-loop__intro section-shell">
              <p className="eyebrow" data-reveal>
                02 / How it cares
              </p>
              <h2 data-reveal>
                看见需求，
                <br />
                然后为你做点什么。
              </h2>
              <p className="care-loop__lead" data-reveal>
                感知、判断、执行和反馈连接成一个完整闭环。机械臂只是动作的最后一步，真正的产品是这套安静而克制的照顾逻辑。
              </p>
            </div>

            <div className="care-loop__body section-shell">
              <div className="care-loop__visual" aria-hidden="true">
                <svg viewBox="0 0 600 600" role="presentation">
                  <circle className="orbit orbit--outer" cx="300" cy="300" r="234" />
                  <circle className="orbit orbit--inner" cx="300" cy="300" r="142" />
                  <path
                    className="care-path"
                    d="M300 66C430 66 534 170 534 300S430 534 300 534 66 430 66 300 170 66 300 66Z"
                  />
                  <g className="care-node" data-loop-node="0" transform="translate(300 66)">
                    <circle r="18" />
                    <text y="5">01</text>
                  </g>
                  <g className="care-node" data-loop-node="1" transform="translate(534 300)">
                    <circle r="18" />
                    <text y="5">02</text>
                  </g>
                  <g className="care-node" data-loop-node="2" transform="translate(300 534)">
                    <circle r="18" />
                    <text y="5">03</text>
                  </g>
                  <g className="care-node" data-loop-node="3" transform="translate(66 300)">
                    <circle r="18" />
                    <text y="5">04</text>
                  </g>
                  <text className="care-loop__visual-word" x="300" y="292" textAnchor="middle">
                    CARE
                  </text>
                  <text className="care-loop__visual-state" x="300" y="326" textAnchor="middle">
                    ACTIVE LOOP
                  </text>
                </svg>
              </div>

              <div className="care-loop__steps">
                <article className="loop-step" data-loop-step="0">
                  <p className="eyebrow">01 / SEE</p>
                  <h3>
                    感知
                    <br />
                    <span>看见被子状态</span>
                  </h3>
                  <p>固定摄像头识别正常覆盖、被子掀开或无法判断。</p>
                  <strong>“正在守护你的睡眠。”</strong>
                </article>
                <article className="loop-step" data-loop-step="1">
                  <p className="eyebrow">02 / VERIFY</p>
                  <h3>
                    判断
                    <br />
                    <span>先确认，再行动</span>
                  </h3>
                  <p>异常必须持续达到阈值，位置无法确认时不执行。</p>
                  <strong>“正在确认是否需要帮你盖好。”</strong>
                </article>
                <article className="loop-step" data-loop-step="2">
                  <p className="eyebrow">03 / ACT</p>
                  <h3>
                    执行
                    <br />
                    <span>沿安全轨迹盖好</span>
                  </h3>
                  <p>机械臂以低速预设轨迹完成盖被，可随时暂停或急停。</p>
                  <strong>“睡吧，我来处理。”</strong>
                </article>
                <article className="loop-step" data-loop-step="3">
                  <p className="eyebrow">04 / RETURN</p>
                  <h3>
                    反馈
                    <br />
                    <span>完成后继续守护</span>
                  </h3>
                  <p>系统复核结果、反馈任务状态并重新进入监测。</p>
                  <strong>“已经帮你盖好了。”</strong>
                </article>
              </div>
            </div>
          </section>

          <section className="vision" id="vision" data-nav-theme="dark">
            <div className="section-shell vision__heading">
              <p className="eyebrow" data-reveal>
                03 / A quieter ecosystem
              </p>
              <h2 data-reveal>
                从盖好一床被子，
                <br />
                到理解每个人的夜晚。
              </h2>
            </div>
            <div className="vision__orbit" aria-label="睡眠照顾生态路线">
              <div className="vision__core" data-reveal>
                <span>NOW</span>
                <strong>主动盖被</strong>
                <small>核心闭环</small>
              </div>
              <div className="vision__node vision__node--1" data-ecosystem-node>
                <span>环境感知</span>
                <small>未来路线</small>
              </div>
              <div className="vision__node vision__node--2" data-ecosystem-node>
                <span>穿戴设备</span>
                <small>未来路线</small>
              </div>
              <div className="vision__node vision__node--3" data-ecosystem-node>
                <span>语音控制</span>
                <small>未来路线</small>
              </div>
              <div className="vision__node vision__node--4" data-ecosystem-node>
                <span>窗帘与灯光</span>
                <small>未来路线</small>
              </div>
              <div className="vision__node vision__node--5" data-ecosystem-node>
                <span>偏好学习</span>
                <small>未来路线</small>
              </div>
            </div>
            <p className="vision__note section-shell" data-reveal>
              未来能力不是已经上线的承诺，而是一条从单一照顾动作出发、逐渐适应个人习惯的产品路线。
            </p>
          </section>

          <section className="closing" id="closing" data-nav-theme="dark">
            <div className="section-shell closing__content">
              <p className="eyebrow" data-reveal>
                04 / Hack the Rest
              </p>
              <h2 data-reveal>
                睡吧，
                <br />
                我来处理。
              </h2>
              <p data-reveal>你的第一个主动式睡眠搭子。</p>
              <a className="closing__cta" href="/welcome" data-reveal>
                <span>了解它如何照顾</span>
                <ArrowUpRight aria-hidden="true" size={20} strokeWidth={1.5} />
              </a>
            </div>
          </section>
        </div>
      </main>

      <footer className="site-footer">
        <div className="section-shell site-footer__top">
          <a className="brand brand--footer" href="#hero">
            <span className="brand__cn">主动睡眠搭子</span>
            <span className="brand__en">Hack the Rest</span>
          </a>
          <p>从记录睡眠，到主动照顾睡眠。</p>
          <nav aria-label="页脚导航">
            <a href="#care-loop">How it cares</a>
            <a href="#vision">Vision</a>
          </nav>
        </div>
        <div className="section-shell site-footer__bottom">
          <span>© 2026 Active Sleep Companion</span>
        </div>
      </footer>
    </div>
  );
}
