"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

/**
 * 月息夜景:星空照片(body 背景)之上的眨眼星空层,带轻微指针视差。
 * blur > 0 时照片层整体虚化(内容不再垫玻璃面板的页面用它保证可读性)。
 */
export default function NightSky({ blur = 0 }: { blur?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 9);

    const disposables: { dispose(): void }[] = [renderer];

    /* ---- 星空 ---- */
    const STAR_COUNT = 900;
    const pos = new Float32Array(STAR_COUNT * 3);
    const phase = new Float32Array(STAR_COUNT);
    const speed = new Float32Array(STAR_COUNT);
    const size = new Float32Array(STAR_COUNT);
    const warm = new Float32Array(STAR_COUNT);
    for (let i = 0; i < STAR_COUNT; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(30 * (0.7 + Math.random() * 0.5));
      v.z = -Math.abs(v.z) - 6;
      pos.set([v.x, v.y * 0.8 + 1.5, v.z], i * 3);
      phase[i] = Math.random() * Math.PI * 2;
      speed[i] = 0.4 + Math.random() * 1.1;
      size[i] = Math.random() * 1.6 + 0.5;
      warm[i] = Math.random() < 0.16 ? 1 : 0;
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    starGeo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    starGeo.setAttribute("aSpeed", new THREE.BufferAttribute(speed, 1));
    starGeo.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    starGeo.setAttribute("aWarm", new THREE.BufferAttribute(warm, 1));
    const starMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 } },
      vertexShader: `attribute float aPhase; attribute float aSpeed; attribute float aSize; attribute float aWarm;
        uniform float uTime; varying float vA; varying float vW;
        void main(){ vW = aWarm;
          vA = 0.45 + 0.55 * sin(uTime * aSpeed + aPhase);
          vec4 mv = modelViewMatrix * vec4(position,1.0);
          gl_PointSize = aSize * (140.0 / -mv.z);
          gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `varying float vA; varying float vW;
        void main(){ float d = length(gl_PointCoord - 0.5);
          float a = (1.0 - smoothstep(0.08, 0.5, d)) * vA;
          vec3 c = mix(vec3(0.85,0.89,1.0), vec3(1.0,0.85,0.55), vW);
          gl_FragColor = vec4(c, a); }`,
    });
    scene.add(new THREE.Points(starGeo, starMat));
    disposables.push(starGeo, starMat);

    /* ---- 布局 / 视差 ---- */
    function layout() {
      renderer.setSize(innerWidth, innerHeight);
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
    }
    layout();

    let px = 0, py = 0;
    const onPointer = (e: PointerEvent) => {
      px = (e.clientX / innerWidth - 0.5) * 2;
      py = (e.clientY / innerHeight - 0.5) * 2;
    };
    addEventListener("resize", layout);
    addEventListener("pointermove", onPointer);

    const clock = new THREE.Clock();
    let raf = 0;
    const lookAt = new THREE.Vector3(0, 0, 0);

    function frame() {
      const t = clock.getElapsedTime();
      starMat.uniforms.uTime.value = t;
      camera.position.x += (px * 0.35 - camera.position.x) * 0.03;
      camera.position.y += (-py * 0.22 - camera.position.y) * 0.03;
      camera.lookAt(lookAt);
      renderer.render(scene, camera);
      if (!reduced) raf = requestAnimationFrame(frame);
    }
    if (reduced) {
      camera.lookAt(lookAt);
      renderer.render(scene, camera);
    } else {
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      removeEventListener("resize", layout);
      removeEventListener("pointermove", onPointer);
      for (const d of disposables) d.dispose();
    };
  }, []);

  return (
    <>
      {/* 星空照片背景 + 半透明蒙版(固定图层,避开 Safari 的 background-attachment:fixed 缺陷) */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-20 bg-cover bg-center"
        style={{
          backgroundImage: "url(/night-sky.jpg)",
          // scale 撑出边缘,避免 blur 后四周露出照片外的黑边
          filter: blur ? `blur(${blur}px)` : undefined,
          transform: blur ? "scale(1.06)" : undefined,
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10"
        style={{ background: `rgba(10, 12, 30, ${blur ? 0.55 : 0.45})` }}
      />
      <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 -z-10 h-full w-full" aria-hidden />
    </>
  );
}
