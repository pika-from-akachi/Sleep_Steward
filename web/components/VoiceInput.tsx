"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Keyboard, Mic, Mic2, Send } from "lucide-react";
import { voiceSourceLabel } from "@/lib/voice/presentation";
import {
  bytesToBase64,
  downsampleTo16Khz,
  floatSamplesToPcm16,
  mergeFloatChunks,
} from "@/lib/voice/pcm";

const QUICK_COMMANDS = ["关灯", "开夜灯", "调高温度"];

interface RecordingSession {
  stream: MediaStream;
  context: AudioContext;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  sink: GainNode;
  chunks: Float32Array[];
  timer: ReturnType<typeof setTimeout>;
}

function recordingErrorMessage(error: unknown) {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "请允许麦克风权限后再试";
  }
  if (error instanceof DOMException && error.name === "NotFoundError") {
    return "没有检测到可用麦克风";
  }
  return "麦克风暂不可用，可改用文字输入";
}

/**
 * 圆形语音按键 + 按需展开的文字输入。
 * compact(睡眠页)不显示快捷指令词条;仪表盘显示。
 */
export default function VoiceInput({
  sessionId,
  compact = false,
}: {
  sessionId?: string;
  compact?: boolean;
}) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [sourceLabel, setSourceLabel] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [textMode, setTextMode] = useState(false);
  const recordingRef = useRef<RecordingSession | null>(null);

  useEffect(
    () => () => {
      const recording = recordingRef.current;
      if (!recording) return;
      clearTimeout(recording.timer);
      recording.stream.getTracks().forEach((track) => track.stop());
      void recording.context.close();
    },
    [],
  );

  async function submit(event?: FormEvent, commandText = text) {
    event?.preventDefault();
    const normalized = commandText.trim();
    if (!normalized || pending) return;

    setPending(true);
    setMessage("");
    setSourceLabel(null);
    try {
      const response = await fetch("/api/voice/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: normalized, sessionId }),
      });
      const data = await response.json().catch(() => ({}));
      setMessage(response.ok ? data.message : data.error || "指令未成功，请再试一次");
      setSourceLabel(response.ok ? voiceSourceLabel(data) : null);
      if (response.ok) setText("");
    } catch {
      setMessage("连接不稳定，请再试一次");
      setSourceLabel(null);
    } finally {
      setPending(false);
    }
  }

  async function finishRecording() {
    const recording = recordingRef.current;
    if (!recording) return;
    recordingRef.current = null;
    clearTimeout(recording.timer);
    setListening(false);
    setTranscribing(true);

    recording.stream.getTracks().forEach((track) => track.stop());
    recording.source.disconnect();
    recording.processor.disconnect();
    recording.sink.disconnect();
    await recording.context.close();

    try {
      const merged = mergeFloatChunks(recording.chunks);
      if (merged.length < recording.context.sampleRate / 4) {
        throw new Error("recording_too_short");
      }
      const pcm = floatSamplesToPcm16(
        downsampleTo16Khz(merged, recording.context.sampleRate),
      );
      const response = await fetch("/api/voice/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audioData: bytesToBase64(pcm) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || typeof data.transcript !== "string") {
        throw new Error(data.error || "语音识别失败");
      }
      const finalTranscript = data.transcript.trim();
      if (!finalTranscript) throw new Error("没有听清，请再试一次");
      setTranscript(finalTranscript);
      setTranscribing(false);
      await submit(undefined, finalTranscript);
    } catch (error) {
      setMessage(
        error instanceof Error && !error.message.includes("recording_too_short")
          ? error.message
          : "说话时间太短，请再试一次",
      );
      setSourceLabel(null);
    } finally {
      setTranscribing(false);
    }
  }

  async function toggleListen() {
    if (listening) {
      await finishRecording();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setTextMode(true);
      setMessage("当前浏览器无法录音，可直接输入文字");
      setSourceLabel(null);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const context = new AudioContext();
      await context.resume();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const sink = context.createGain();
      const chunks: Float32Array[] = [];
      sink.gain.value = 0;
      processor.onaudioprocess = (event) => {
        chunks.push(event.inputBuffer.getChannelData(0).slice());
      };
      source.connect(processor);
      processor.connect(sink);
      sink.connect(context.destination);

      const timer = setTimeout(() => void finishRecording(), 8_000);
      recordingRef.current = {
        stream,
        context,
        source,
        processor,
        sink,
        chunks,
        timer,
      };
      setMessage("");
      setSourceLabel(null);
      setTranscript("");
      setListening(true);
    } catch (error) {
      setListening(false);
      setTextMode(true);
      setMessage(recordingErrorMessage(error));
      setSourceLabel(null);
    }
  }

  return (
    <section className="flex w-full flex-col items-center">
      <div className="mb-5 flex items-center justify-center gap-2 text-[11px] tracking-[0.26em] text-cream-dim">
        <Mic2 size={14} strokeWidth={1.4} />
        语音指令
      </div>

      <div className="grid w-full max-w-md grid-cols-1 items-center justify-items-center gap-3 sm:grid-cols-[76px_minmax(0,1fr)] sm:justify-items-stretch sm:gap-5">
        <button
          type="button"
          onClick={toggleListen}
          disabled={pending || transcribing}
          aria-label={listening ? "停止聆听" : "开始说话"}
          className={`relative grid h-[76px] w-[76px] justify-self-center place-items-center rounded-full border transition-colors disabled:opacity-50 ${
            listening
              ? "border-moon/70 bg-moon/20 text-moon"
              : "glass text-cream-dim hover:border-moon/45 hover:text-cream"
          }`}
        >
          {listening && (
            <motion.span
              aria-hidden
              className="absolute inset-0 rounded-full border border-moon/50"
              animate={{ scale: [1, 1.45], opacity: [0.6, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
            />
          )}
          <Mic size={26} strokeWidth={1.5} />
        </button>

        <div
          aria-live="polite"
          className="flex min-h-[76px] w-full items-center border-t border-hair pt-3 text-center sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0 sm:text-left"
        >
          <div className="min-w-0 w-full">
            <p className="mb-1 text-[9.5px] tracking-[0.16em] text-cream-dim/60">
              识别文字
            </p>
            <p className="break-words text-[13px] leading-6 text-cream">
              {listening
                ? "正在聆听…"
                : transcribing
                  ? "正在识别…"
                  : transcript
                    ? `“${transcript}”`
                    : "尚未识别"}
            </p>
          </div>
        </div>
      </div>

      <div aria-live="polite" className="mt-3.5 min-h-[42px] text-center">
        {sourceLabel && !listening && !pending && (
          <p className="mb-0.5 flex items-center justify-center gap-1.5 text-[10px] text-moon/80">
            <span className="h-1 w-1 rounded-full bg-moon/70" aria-hidden />
            {sourceLabel}
          </p>
        )}
        <p className="text-[11.5px] leading-5 text-cream-dim">
          {listening
            ? "正在聆听，再次点击可结束"
            : transcribing
              ? "正在生成最终文字"
              : pending
                ? "正在执行"
                : message || "单击开始说话，8 秒后自动结束"}
        </p>
      </div>

      {!compact && (
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {QUICK_COMMANDS.map((command) => (
            <button
              key={command}
              type="button"
              disabled={pending}
              onClick={() => submit(undefined, command)}
              className="rounded-full border border-hair px-3.5 py-1.5 text-[10.5px] text-cream-dim transition-colors hover:border-moon/35 hover:text-cream disabled:opacity-40"
            >
              {command}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence initial={false}>
        {textMode && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onSubmit={(event) => submit(event)}
            className="mt-3 w-full max-w-sm overflow-hidden"
          >
            <div className="glass flex items-center rounded-2xl p-1.5">
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
                maxLength={200}
                placeholder="关灯，或者把房间调暖一点"
                aria-label="输入语音指令"
                className="min-w-0 flex-1 bg-transparent px-3 py-2 text-[12.5px] text-cream outline-none placeholder:text-cream-dim/55"
              />
              <button
                type="submit"
                disabled={pending || !text.trim()}
                aria-label="执行指令"
                className="rounded-xl bg-moon/15 p-2.5 text-moon transition-colors hover:bg-moon/25 disabled:opacity-30"
              >
                <Send size={15} strokeWidth={1.6} />
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={() => setTextMode((v) => !v)}
        className="mt-3 flex items-center gap-1.5 text-[10.5px] tracking-[0.14em] text-cream-dim/70 transition-colors hover:text-cream"
      >
        <Keyboard size={12} strokeWidth={1.5} />
        {textMode ? "收起文字输入" : "改用文字输入"}
      </button>
    </section>
  );
}
