---
name: windows-computer-use
description: "Use when Codex needs to inspect or control local Windows desktop apps through a local MCP server: screenshots, mouse movement, clicks, typing, hotkeys, and waits. Trigger for requests to use Windows mouse/keyboard, operate desktop apps, automate repetitive GUI work, or approximate Computer Use on Windows."
---

# Windows Computer Use

Use the `windows-computer-use` MCP tools for local Windows GUI automation.

## Workflow

1. Start with `observe` for a combined state snapshot unless a narrower tool is clearly enough.
2. Use exact title or `hwnd` when window ambiguity exists.
3. Use `act_and_observe` for most GUI steps so actions are immediately verified.
4. Ask before irreversible or sensitive actions such as submitting payments, deleting files, changing passwords, sending messages, publishing content, or accepting security prompts.
5. Prefer app APIs, CLI, or browser automation when they are safer and more deterministic than GUI control.

## Tool Notes

- `observe` returns active window, mouse, visible windows, and optional screenshot/OCR/controls in one call.
- `act` runs a single safe action by name.
- `act_and_observe` runs one action or a batch and then returns a fresh observation.
- `list_windows` finds visible windows by title; use it before broad screenshots when possible.
- `active_window` reports the foreground window.
- `focus_window` brings a matching app window to the front; use `exact=true` and `exclude` when names collide.
- `focus_window_handle`, `minimize_window_handle`, and `restore_window_handle` control the exact `hwnd`; prefer these after `list_windows` in ambiguous cases.
- `wait_for_window`, `switch_app`, and `open_app` support app workflows.
- `screenshot` saves a PNG; pass `all_screens=false` for faster primary-monitor capture.
- `screenshot_region` captures a smaller rectangle when only one UI area matters.
- `ocr_screen`, `find_text`, `click_text`, and `wait_for_text` use OCR. Tesseract is configured at `C:\Program Files\Tesseract-OCR\tesseract.exe` when present.
- `list_controls`, `find_control`, `click_control`, and `type_into_control` use Windows UI Automation. Prefer these over coordinates when controls are exposed by the app.
- `wait_for_control`, `invoke_control`, and `set_control_value` use stronger UI Automation patterns when available and fall back safely where implemented.
- `mouse_move`, `mouse_click`, and `mouse_double_click` use screen coordinates.
- `right_click`, `scroll`, and `drag` cover common pointer actions.
- `type_text` types into the currently focused control.
- `paste_text` places text on the clipboard and pastes it with `ctrl,v`; prefer this for longer text.
- `clipboard_read` reads current clipboard text.
- `press_key` sends one key, and `hotkey` sends key combinations such as `ctrl,l`.
- `wait` pauses for visual changes before the next screenshot.
- `batch_actions` runs non-screenshot actions in one MCP call. Prefer it for sequences like focus window, click field, type text, press enter, wait.

Coordinates are physical screen pixels. After clicking or typing, wait briefly and take another screenshot to verify the result.
