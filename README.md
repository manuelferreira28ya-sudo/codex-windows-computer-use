# Codex Windows Computer Use

A local Windows desktop automation plugin for Codex.

It gives Codex a practical Windows approximation of Computer Use: observe the desktop, focus windows, use OCR and Windows UI Automation, click/type/scroll/drag, and verify actions through observe -> act -> observe loops.

This is not the official OpenAI Computer Use plugin. It is a community/local Windows plugin built around Python, Win32 APIs, Tesseract OCR, and Windows UI Automation.

## What It Can Do

- Observe desktop state with `observe`
- Run actions and immediately verify with `act_and_observe`
- Capture full-screen, primary-monitor, or region screenshots
- Focus, restore, and minimize windows by exact `hwnd`
- Avoid title collisions like `Roblox` vs `Roblox Studio` with exact matching
- Type text normally or paste quickly with clipboard support
- Click, right-click, double-click, scroll, and drag
- Use OCR with Tesseract for `find_text`, `click_text`, and `wait_for_text`
- Use Windows UI Automation for controls with `list_controls`, `find_control`, `invoke_control`, `set_control_value`, and `type_into_control`

## Requirements

- Windows
- Codex Desktop with local plugins enabled
- Python 3.10+
- Python packages:
  - `Pillow`
  - `pytesseract`
- Optional but recommended:
  - Tesseract OCR for Windows

Install Python dependencies:

```powershell
python -m pip install -r plugins/windows-computer-use/requirements.txt
```

Install Tesseract OCR with winget:

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

The plugin automatically looks for Tesseract at:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

You can override this with the `TESSERACT_CMD` environment variable.

## Install In Codex

Add this repository as a local/git marketplace in your Codex config.

Example:

```toml
[marketplaces.windows-computer-use]
source_type = "git"
source = "https://github.com/YOUR_USERNAME/codex-windows-computer-use.git"

[plugins."windows-computer-use@windows-computer-use"]
enabled = true
```

Then restart Codex Desktop.

## Safety

This plugin can control your real desktop.

Recommended rules:

- Do not use it to submit payments, publish content, delete files, send messages, change passwords, or accept security prompts without explicit confirmation.
- Prefer `observe` before acting.
- Prefer `act_and_observe` over blind sequences.
- Prefer UI Automation or OCR over fragile coordinates when possible.
- Keep tests harmless and reversible.

The included `close_window` tool requires `confirm=true` and should only be used after explicit user approval.

## Example Workflows

Observe current desktop state:

```json
{
  "screenshot": true,
  "ocr": true,
  "controls": true,
  "all_screens": false
}
```

Focus the exact Roblox client without selecting Roblox Studio:

```json
{
  "query": "Roblox",
  "exact": true,
  "timeout_seconds": 5
}
```

Run an action and verify it:

```json
{
  "actions": [
    {
      "tool": "focus_window_handle",
      "arguments": { "hwnd": 123456 }
    },
    {
      "tool": "paste_text",
      "arguments": { "text": "Hello from Codex Windows Computer Use" }
    }
  ],
  "observe": {
    "screenshot": true,
    "ocr": true,
    "all_screens": false
  }
}
```

## Status

Alpha. Useful for real desktop automation, but still not equivalent to the official native macOS Computer Use integration.

Known gaps:

- No proprietary/native OpenAI Computer Use runtime integration
- OCR quality depends on Tesseract and screen clarity
- UI Automation works best in traditional Windows apps; browser/Electron/game UIs may expose limited controls
- Some apps require screenshots/OCR/coordinates as fallback

## License

MIT
