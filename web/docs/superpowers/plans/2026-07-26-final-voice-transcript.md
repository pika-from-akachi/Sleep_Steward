# Final Voice Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the browser's final speech transcript beside the microphone before the existing command result.

**Architecture:** A focused pure helper extracts final transcript segments from the browser result collection. `VoiceInput` stores that text in local state and renders a responsive status region without changing the command API or hardware execution path.

**Tech Stack:** TypeScript, React 19, Next.js 16, Vitest, Tailwind CSS

## Global Constraints

- Show only final recognition text, never interim text.
- Do not persist the transcript beyond component state.
- Keep existing local command, StepFun, and hardware behavior unchanged.
- Desktop places the transcript to the right of the microphone; mobile places it below.

---

### Task 1: Extract final transcript segments

**Files:**
- Create: `lib/voice/transcript.ts`
- Test: `lib/voice/transcript.test.ts`

**Interfaces:**
- Produces: `finalSpeechTranscript(results: ArrayLike<SpeechRecognitionResultLike>): string`
- Produces: `SpeechRecognitionResultLike`, containing `isFinal` and a first alternative with `transcript`

- [ ] **Step 1: Write the failing tests**

Test that multiple final segments are trimmed and joined, interim segments are ignored, and whitespace-only results return an empty string.

- [ ] **Step 2: Verify the tests fail**

Run: `npx vitest run lib/voice/transcript.test.ts`

Expected: FAIL because `./transcript` does not exist.

- [ ] **Step 3: Implement the pure helper**

Iterate over the array-like results, keep entries where `isFinal` is true, trim each first alternative transcript, discard empty segments, and join them with one space.

- [ ] **Step 4: Verify the tests pass**

Run: `npx vitest run lib/voice/transcript.test.ts`

Expected: all transcript tests pass.

### Task 2: Render final transcript in VoiceInput

**Files:**
- Modify: `components/VoiceInput.tsx`

**Interfaces:**
- Consumes: `finalSpeechTranscript(results)` from Task 1

- [ ] **Step 1: Add transcript state and event handling**

Set `interimResults` to false, clear transcript at the start of each listening session, extract final text in `onresult`, store it, and submit only when non-empty.

- [ ] **Step 2: Add responsive transcript presentation**

Wrap the microphone and transcript region in a stable responsive grid. Display “正在聆听…” while listening, the quoted final transcript after recognition, and a neutral placeholder before first use. Preserve the separate source label and execution result below.

- [ ] **Step 3: Run complete verification**

Run: `npm test`

Run: `npx tsc --noEmit`

Run: `npm run lint`

Run: `npm run build`

Expected: all commands pass.

- [ ] **Step 4: Verify responsive behavior in browser**

Check the dashboard at the default desktop viewport and at `390x844`. Confirm the transcript region does not overlap, resize the microphone, or cause horizontal overflow.

- [ ] **Step 5: Commit**

```bash
git add lib/voice/transcript.ts lib/voice/transcript.test.ts components/VoiceInput.tsx docs/superpowers/specs/2026-07-26-final-voice-transcript-design.md docs/superpowers/plans/2026-07-26-final-voice-transcript.md
git commit -m "feat: show final voice transcript"
```
