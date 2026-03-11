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
- [ ] Add support for local Whisper models (faster-whisper/whisper.cpp) (#7)
- [ ] Implement 'Prompt Presets' for different command variants (#8)
- [ ] Add post-processing hooks for transcribed text (#9)

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
