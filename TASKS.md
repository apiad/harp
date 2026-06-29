# Tasks

Legend:

- [ ] Todo
- [/] In Progress (@user) <-- indicates who is doing it
- [x] Done

**INSTRUCTIONS:**

Keep task descriptions short but descriptive. Do not add implementation details, those belong in task-specific plans. When adding new tasks, consider grouping them into meaningful clusters such as UX, Backend, Logic, Refactoring, etc.

Put done tasks into the Archive.

---

## Active Tasks

### UX & Customization
- [ ] Configure custom hotkeys via .env or YAML (#5)
- [ ] Support for multiple international keyboard layouts (ISO, etc.) (#13)

### AI Features
- [ ] Add post-processing hooks for transcribed text (#9) — deferred to slice D of the dictation redesign

### Dictation (streaming redesign follow-ups)
- [ ] Slice B — custom hotkeys / VAD-driven auto-stop for streaming sessions
- [ ] Slice D — post-processing hooks layered on top of the committed prefix
- [ ] Live empirical tuning of `stream_slide_interval` per model/device (needs a mic-equipped host)

### Long-form streaming engine (VAD-segmented)
> Spec: `docs/superpowers/specs/2026-06-27-streaming-vad-transcription-engine-design.md`
> Plan: `docs/superpowers/plans/2026-06-27-streaming-vad-engine-slice1.md`
- [x] Slice 2 — `harp start` hotkey daemon on the new engine (shared `_build_engine` fast path: int8 + stream_beam_size); finalize-only default keeps it real-time (2026-06-27)
- [x] Slice 3 — `harp transcribe -o` live file sink; refreshed `docs/{design,library,cli,index}.md` + README; CHANGELOG; added `AGENTS.md` + `know-how/streaming-engine.md` (2026-06-27)
- [ ] Hallucination on short/quiet VAD chunks with small models (`tiny` emits repeated non-English tokens on near-silence) — mitigate by skipping sub-threshold-speech chunks or using `no_speech_prob`; `base` is unaffected
- [ ] Tune `stream_warmup` (initial-output latency vs short-dictation single-decode) and decide the default transient mode

### Infrastructure
- [ ] Implement Voice Activity Detection (VAD) for auto-stop (#10)
- [ ] Integrate XDG Global Shortcuts portal (D-Bus) (#11)

### Portability
- [ ] Research and scaffold macOS support (CoreAudio/Quartz) (#12)

### Testing

---

## Archive

> Done tasks go here, in the order they where finished, with a finished date.

- [x] Implement initial MVP (Wayland/evdev) (See plan: `plans/implement-mvp.md`) (2026-03-03)
- [x] Fix terminal pollution (^@) via uinput interceptor (See plan: `plans/fix-terminal-pollution.md`) (2026-03-03)
- [x] Implement audio capture and test WAV saving (See plan: `plans/audio-capture.md`) (2026-03-03)
- [x] Implement batch audio transcription via OpenRouter (See plan: `plans/audio-transcription.md`) (2026-03-03)
- [x] Implement keyboard emulation for typing transcriptions (See plan: `plans/keyboard-emulation.md`) (2026-03-03)
- [x] Implement 'Command' mode (Ctrl + Shift + Space) for voice instructions (2026-03-03)
- [x] Implement Clipboard Context & Auto-Copy features (See plan: `plans/clipboard-context-features.md`) (2026-03-04)
- [x] Implement voice-based integration test (#14) (See plan: `plans/voice-integration-test.md`) (2026-03-04)
- [x] Implement CLI overhaul and YAML configuration system (See plan: `plans/cli-overhaul-config.md`) (2026-03-11)
- [x] Implement local-first Whisper refactor and high-speed concurrent transcription (See plan: `plans/local-first-whisper-refactor.md`) (2026-03-11)
- [x] Real-time streaming dictation with back-patch typing + removal of cloud LLM/command mode (See plan: `docs/superpowers/plans/2026-05-18-streaming-backpatch-dictation-plan.html`) (2026-05-18)
- [x] Library-first refactor + clipboard-paste delivery (See plan: `docs/superpowers/plans/2026-06-01-library-first-clipboard-paste-plan.md`) (2026-06-01)
- [x] VAD-segmented streaming engine — Slice 1: TranscriptEvent, Silero VAD, finalize-once-and-drop engine, FileSource, `harp transcribe <file>`, audio-driven step cadence (See plan: `docs/superpowers/plans/2026-06-27-streaming-vad-engine-slice1.md`) (2026-06-27)
