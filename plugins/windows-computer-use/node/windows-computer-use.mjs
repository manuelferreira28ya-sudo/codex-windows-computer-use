#!/usr/bin/env node
import { createInterface } from "node:readline";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const TESSERACT = process.env.TESSERACT_CMD || "C:\\Program Files\\Tesseract-OCR\\tesseract.exe";

function send(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function textResult(text) {
  return { content: [{ type: "text", text }] };
}

function psString(value) {
  return `'${String(value ?? "").replaceAll("'", "''")}'`;
}

function runPowerShell(script) {
  const encoded = Buffer.from(`$ProgressPreference='SilentlyContinue';\n${script}`, "utf16le").toString("base64");
  const out = execFileSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], {
    encoding: "utf8",
    windowsHide: true,
    maxBuffer: 20 * 1024 * 1024,
  }).trim();
  return out ? JSON.parse(out) : null;
}

const win32Prelude = `
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WCUWin32 {
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT pt);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int nIndex);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, int data, UIntPtr extraInfo);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extraInfo);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
}
"@ -ErrorAction SilentlyContinue
`;

function winScript(body) {
  return `${win32Prelude}\n${body}`;
}

function listWindowsPayload(args = {}) {
  const query = String(args.query ?? "").toLowerCase();
  const limit = Number(args.limit ?? 30);
  return runPowerShell(winScript(`
$query = ${psString(query)}
$active = [WCUWin32]::GetForegroundWindow()
$items = New-Object System.Collections.Generic.List[object]
[WCUWin32]::EnumWindows({
  param([IntPtr]$hwnd, [IntPtr]$lparam)
  if (-not [WCUWin32]::IsWindowVisible($hwnd)) { return $true }
  $len = [WCUWin32]::GetWindowTextLength($hwnd)
  if ($len -le 0) { return $true }
  $sb = New-Object System.Text.StringBuilder ($len + 1)
  [void][WCUWin32]::GetWindowText($hwnd, $sb, $sb.Capacity)
  $title = $sb.ToString()
  if ($query.Length -gt 0 -and -not $title.ToLower().Contains($query)) { return $true }
  $rect = New-Object WCUWin32+RECT
  [void][WCUWin32]::GetWindowRect($hwnd, [ref]$rect)
  if ($rect.Right -le $rect.Left -or $rect.Bottom -le $rect.Top) { return $true }
  $items.Add([pscustomobject]@{
    hwnd = [int64]$hwnd
    title = $title
    rect = @($rect.Left, $rect.Top, $rect.Right, $rect.Bottom)
    active = ($hwnd -eq $active)
  })
  return $true
}, [IntPtr]::Zero) | Out-Null
$items | Select-Object -First ${limit} | ConvertTo-Json -Compress
`)) ?? [];
}

function activeWindowPayload() {
  return runPowerShell(winScript(`
$hwnd = [WCUWin32]::GetForegroundWindow()
$len = [WCUWin32]::GetWindowTextLength($hwnd)
$sb = New-Object System.Text.StringBuilder ($len + 1)
[void][WCUWin32]::GetWindowText($hwnd, $sb, $sb.Capacity)
$rect = New-Object WCUWin32+RECT
[void][WCUWin32]::GetWindowRect($hwnd, [ref]$rect)
[pscustomobject]@{ hwnd = [int64]$hwnd; title = $sb.ToString(); rect = @($rect.Left,$rect.Top,$rect.Right,$rect.Bottom) } | ConvertTo-Json -Compress
`));
}

function mousePayload() {
  return runPowerShell(winScript(`
$pt = New-Object WCUWin32+POINT
[void][WCUWin32]::GetCursorPos([ref]$pt)
[pscustomobject]@{ x = $pt.X; y = $pt.Y; screen_size = @([WCUWin32]::GetSystemMetrics(0), [WCUWin32]::GetSystemMetrics(1)) } | ConvertTo-Json -Compress
`));
}

function screenshotPayload(args = {}) {
  const outDir = args.directory || join(tmpdir(), "windows-computer-use");
  mkdirSync(outDir, { recursive: true });
  const path = join(outDir, `screenshot-${Date.now()}-${Math.random().toString(16).slice(2)}.png`);
  const bbox = Array.isArray(args.bbox) ? args.bbox : null;
  const allScreens = Boolean(args.all_screens);
  const script = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$path = ${psString(path)}
${bbox ? `$left=${bbox[0]}; $top=${bbox[1]}; $width=${bbox[2] - bbox[0]}; $height=${bbox[3] - bbox[1]}` : allScreens ? `$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen; $left=$bounds.Left; $top=$bounds.Top; $width=$bounds.Width; $height=$bounds.Height` : `$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $left=$bounds.Left; $top=$bounds.Top; $width=$bounds.Width; $height=$bounds.Height`}
$bmp = New-Object System.Drawing.Bitmap $width, $height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($left, $top, 0, 0, $bmp.Size)
$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
[pscustomobject]@{ path = $path; size = @($width, $height); all_screens = ${allScreens ? "$true" : "$false"}; bbox = ${bbox ? `@(${bbox.join(",")})` : "$null"} } | ConvertTo-Json -Compress
`;
  return runPowerShell(script);
}

function keyCode(name) {
  const k = String(name).toLowerCase();
  const map = { backspace: 8, tab: 9, enter: 13, shift: 16, ctrl: 17, control: 17, alt: 18, esc: 27, escape: 27, space: 32, pageup: 33, pagedown: 34, end: 35, home: 36, left: 37, up: 38, right: 39, down: 40, delete: 46, win: 91, cmd: 91 };
  if (map[k]) return map[k];
  if (/^[a-z]$/.test(k)) return k.toUpperCase().charCodeAt(0);
  if (/^[0-9]$/.test(k)) return k.charCodeAt(0);
  if (/^f([1-9]|1[0-9]|2[0-4])$/.test(k)) return 111 + Number(k.slice(1));
  throw new Error(`Unsupported key: ${name}`);
}

function doWinAction(kind, args = {}) {
  const script = winScript(`
function KeyDown($vk) { [WCUWin32]::keybd_event([byte]$vk, 0, 0, [UIntPtr]::Zero) }
function KeyUp($vk) { [WCUWin32]::keybd_event([byte]$vk, 0, 2, [UIntPtr]::Zero) }
$kind = ${psString(kind)}
switch ($kind) {
  "focus_window_handle" { [WCUWin32]::ShowWindow([IntPtr][int64]${Number(args.hwnd ?? 0)}, 9) | Out-Null; Start-Sleep -Milliseconds 50; [WCUWin32]::SetForegroundWindow([IntPtr][int64]${Number(args.hwnd ?? 0)}) | Out-Null }
  "minimize_window_handle" { [WCUWin32]::ShowWindow([IntPtr][int64]${Number(args.hwnd ?? 0)}, 6) | Out-Null }
  "restore_window_handle" { [WCUWin32]::ShowWindow([IntPtr][int64]${Number(args.hwnd ?? 0)}, 9) | Out-Null; [WCUWin32]::SetForegroundWindow([IntPtr][int64]${Number(args.hwnd ?? 0)}) | Out-Null }
  "mouse_move" { [WCUWin32]::SetCursorPos(${Number(args.x ?? 0)}, ${Number(args.y ?? 0)}) | Out-Null }
  "mouse_click" { ${args.x !== undefined && args.y !== undefined ? `[WCUWin32]::SetCursorPos(${Number(args.x)}, ${Number(args.y)}) | Out-Null; Start-Sleep -Milliseconds 30` : ""}; [WCUWin32]::mouse_event(0x0002,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 30; [WCUWin32]::mouse_event(0x0004,0,0,0,[UIntPtr]::Zero) }
  "right_click" { ${args.x !== undefined && args.y !== undefined ? `[WCUWin32]::SetCursorPos(${Number(args.x)}, ${Number(args.y)}) | Out-Null; Start-Sleep -Milliseconds 30` : ""}; [WCUWin32]::mouse_event(0x0008,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 30; [WCUWin32]::mouse_event(0x0010,0,0,0,[UIntPtr]::Zero) }
  "scroll" { ${args.x !== undefined && args.y !== undefined ? `[WCUWin32]::SetCursorPos(${Number(args.x)}, ${Number(args.y)}) | Out-Null;` : ""} [WCUWin32]::mouse_event(0x0800,0,0,${Number(args.clicks ?? args.amount ?? 1) * 120},[UIntPtr]::Zero) }
  "press_key" { $vk=${args.key ? keyCode(args.key) : 0}; KeyDown $vk; Start-Sleep -Milliseconds ${Number(args.hold_seconds ?? 0.03) * 1000}; KeyUp $vk }
  "hotkey" { $keys=@(${String(args.keys ?? "").split(",").map((k) => keyCode(k.trim())).join(",")}); foreach($k in $keys){KeyDown $k; Start-Sleep -Milliseconds 20}; [array]::Reverse($keys); foreach($k in $keys){KeyUp $k; Start-Sleep -Milliseconds 20} }
  "close_window" { if (-not ${args.confirm ? "$true" : "$false"}) { throw "close_window requires confirm=true" }; [WCUWin32]::PostMessage([IntPtr][int64]${Number(args.hwnd ?? 0)}, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
}
[pscustomobject]@{ ok = $true; tool = $kind } | ConvertTo-Json -Compress
`);
  return runPowerShell(script);
}

function pasteText(args = {}) {
  const text = String(args.text ?? "");
  runPowerShell(`
Set-Clipboard -Value ${psString(text)}
Start-Sleep -Milliseconds ${Number(args.before_paste_seconds ?? 0.05) * 1000}
`);
  doWinAction("hotkey", { keys: "ctrl,v" });
  return { ok: true };
}

function clipboardRead() {
  return { text: runPowerShell(`Get-Clipboard | ConvertTo-Json -Compress`) ?? "" };
}

function typeText(args = {}) {
  const text = String(args.text ?? "");
  for (const ch of text) {
    if (ch === "\r") continue;
    if (ch === "\n") doWinAction("press_key", { key: "enter" });
    else pasteText({ text: ch, before_paste_seconds: 0 });
  }
  return { ok: true };
}

function listControlsPayload(args = {}) {
  const query = psString(args.window_query ?? "");
  const limit = Number(args.limit ?? 80);
  return runPowerShell(`
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$query = ${query}.ToLower()
$root = [System.Windows.Automation.AutomationElement]::RootElement
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$target = $null
foreach ($w in $windows) { $name = $w.Current.Name; if ($name -and ($query.Length -eq 0 -or $name.ToLower().Contains($query))) { $target = $w; break } }
if ($null -eq $target) { @{ error = "No matching window" } | ConvertTo-Json -Compress; exit 0 }
$items = New-Object System.Collections.Generic.List[object]
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($el in $all) {
  if ($items.Count -ge ${limit}) { break }
  $rect = $el.Current.BoundingRectangle
  $name = $el.Current.Name
  $aid = $el.Current.AutomationId
  $ctype = $el.Current.ControlType.ProgrammaticName
  if (($name -or $aid) -and $rect.Width -gt 0 -and $rect.Height -gt 0) {
    $items.Add([pscustomobject]@{ name=$name; automationId=$aid; controlType=$ctype; rect=@([int]$rect.Left,[int]$rect.Top,[int]$rect.Right,[int]$rect.Bottom) })
  }
}
[pscustomobject]@{ window = $target.Current.Name; controls = $items } | ConvertTo-Json -Depth 4 -Compress
`);
}

function ocrPayload(args = {}) {
  if (!existsSync(TESSERACT)) throw new Error(`Tesseract not found at ${TESSERACT}`);
  const shot = screenshotPayload(args);
  const outBase = shot.path.replace(/\\.png$/i, "");
  spawnSync(TESSERACT, [shot.path, outBase, "tsv"], { windowsHide: true });
  const tsv = readFileSync(`${outBase}.tsv`, "utf8");
  const lines = tsv.trim().split(/\r?\n/).slice(1);
  const words = [];
  for (const line of lines) {
    const cols = line.split("\t");
    if (cols.length < 12) continue;
    const text = cols[11]?.trim();
    if (!text) continue;
    const left = Number(cols[6]), top = Number(cols[7]), width = Number(cols[8]), height = Number(cols[9]), conf = Number(cols[10]);
    const dx = Array.isArray(args.bbox) ? Number(args.bbox[0]) : 0;
    const dy = Array.isArray(args.bbox) ? Number(args.bbox[1]) : 0;
    words.push({ text, confidence: conf, rect: [left + dx, top + dy, left + width + dx, top + height + dy] });
  }
  return { words: words.slice(0, Number(args.limit ?? 200)) };
}

function observePayload(args = {}) {
  const payload = {
    active_window: activeWindowPayload(),
    mouse: mousePayload(),
    windows: listWindowsPayload({ limit: args.window_limit ?? 12 }),
  };
  if (args.screenshot ?? true) payload.screenshot = screenshotPayload(args);
  if (args.ocr) {
    try { payload.ocr = ocrPayload({ ...args, limit: args.ocr_limit ?? 80 }); } catch (error) { payload.ocr_error = String(error.message || error); }
  }
  if (args.controls) {
    try { payload.controls = listControlsPayload({ window_query: args.window_query ?? payload.active_window.title, limit: args.control_limit ?? 80 }); } catch (error) { payload.controls_error = String(error.message || error); }
  }
  return payload;
}

function waitForWindow(args = {}) {
  const query = String(args.query ?? "").toLowerCase();
  const exact = Boolean(args.exact);
  const exclude = (args.exclude ?? []).map((x) => String(x).toLowerCase());
  const end = Date.now() + Number(args.timeout_seconds ?? 10) * 1000;
  while (Date.now() < end) {
    const windows = listWindowsPayload({ limit: 100 }).filter((w) => !exclude.some((e) => w.title.toLowerCase().includes(e)));
    const match = windows.find((w) => exact ? w.title.toLowerCase().trim() === query : w.title.toLowerCase().includes(query));
    if (match) return { match };
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200);
  }
  throw new Error(`Timed out waiting for window: ${args.query}`);
}

function runAction(tool, args = {}) {
  if (["focus_window_handle", "minimize_window_handle", "restore_window_handle", "mouse_move", "mouse_click", "right_click", "scroll", "press_key", "hotkey", "close_window"].includes(tool)) return doWinAction(tool, args);
  if (tool === "paste_text") return pasteText(args);
  if (tool === "type_text") return typeText(args);
  if (tool === "wait") { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, Number(args.seconds ?? 1) * 1000); return { ok: true }; }
  if (tool === "switch_app") { const found = waitForWindow(args).match; return doWinAction("focus_window_handle", { hwnd: found.hwnd }); }
  throw new Error(`Unsupported action: ${tool}`);
}

function batchActions(args = {}) {
  const results = [];
  for (const [index, action] of (args.actions ?? []).entries()) {
    runAction(action.tool, action.arguments ?? {});
    results.push({ index, tool: action.tool, status: "ok" });
    if (action.pause_after_seconds) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, Number(action.pause_after_seconds) * 1000);
  }
  return { count: results.length, results };
}

const tools = {
  observe: { description: "Return combined desktop observation.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => observePayload(a) },
  act: { description: "Run one safe action.", inputSchema: { type: "object", properties: { tool: { type: "string" }, arguments: { type: "object" } }, required: ["tool"], additionalProperties: false }, handler: (a) => ({ tool: a.tool, result: runAction(a.tool, a.arguments ?? {}) }) },
  act_and_observe: { description: "Run action(s), then observe.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => ({ action: a.actions ? batchActions({ actions: a.actions }) : { tool: a.tool, result: runAction(a.tool, a.arguments ?? {}) }, observation: observePayload(a.observe ?? {}) }) },
  list_windows: { description: "List visible windows.", inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer" } }, additionalProperties: false }, handler: listWindowsPayload },
  active_window: { description: "Return foreground window.", inputSchema: { type: "object", properties: {}, additionalProperties: false }, handler: activeWindowPayload },
  wait_for_window: { description: "Wait for visible window.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: waitForWindow },
  switch_app: { description: "Wait for and focus app window.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => { const found = waitForWindow(a).match; return doWinAction("focus_window_handle", { hwnd: found.hwnd }); } },
  focus_window_handle: { description: "Focus by hwnd.", inputSchema: { type: "object", properties: { hwnd: { type: "integer" } }, required: ["hwnd"], additionalProperties: false }, handler: (a) => doWinAction("focus_window_handle", a) },
  minimize_window_handle: { description: "Minimize by hwnd.", inputSchema: { type: "object", properties: { hwnd: { type: "integer" } }, required: ["hwnd"], additionalProperties: false }, handler: (a) => doWinAction("minimize_window_handle", a) },
  restore_window_handle: { description: "Restore by hwnd.", inputSchema: { type: "object", properties: { hwnd: { type: "integer" } }, required: ["hwnd"], additionalProperties: false }, handler: (a) => doWinAction("restore_window_handle", a) },
  screenshot: { description: "Capture screenshot.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: screenshotPayload },
  ocr_screen: { description: "Run OCR.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: ocrPayload },
  list_controls: { description: "List UI Automation controls.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: listControlsPayload },
  mouse_position: { description: "Return mouse position.", inputSchema: { type: "object", properties: {}, additionalProperties: false }, handler: mousePayload },
  mouse_move: { description: "Move mouse.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("mouse_move", a) },
  mouse_click: { description: "Click mouse.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("mouse_click", a) },
  right_click: { description: "Right-click mouse.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("right_click", a) },
  scroll: { description: "Scroll wheel.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("scroll", a) },
  press_key: { description: "Press key.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("press_key", a) },
  hotkey: { description: "Press hotkey.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: (a) => doWinAction("hotkey", a) },
  paste_text: { description: "Paste text using clipboard.", inputSchema: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: true }, handler: pasteText },
  type_text: { description: "Type text.", inputSchema: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: true }, handler: typeText },
  clipboard_read: { description: "Read clipboard text.", inputSchema: { type: "object", properties: {}, additionalProperties: false }, handler: clipboardRead },
  wait: { description: "Wait seconds.", inputSchema: { type: "object", properties: { seconds: { type: "number" } }, required: ["seconds"], additionalProperties: false }, handler: (a) => runAction("wait", a) },
  batch_actions: { description: "Run multiple actions.", inputSchema: { type: "object", properties: {}, additionalProperties: true }, handler: batchActions },
};

function handle(req) {
  if (req.method === "initialize") return { jsonrpc: "2.0", id: req.id, result: { protocolVersion: req.params?.protocolVersion ?? "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: "windows-computer-use", version: "0.1.0-node" } } };
  if (req.method === "notifications/initialized") return null;
  if (req.method === "tools/list") return { jsonrpc: "2.0", id: req.id, result: { tools: Object.entries(tools).map(([name, spec]) => ({ name, description: spec.description, inputSchema: spec.inputSchema })) } };
  if (req.method === "tools/call") {
    const name = req.params?.name;
    if (!tools[name]) throw new Error(`Unknown tool: ${name}`);
    return { jsonrpc: "2.0", id: req.id, result: textResult(JSON.stringify(tools[name].handler(req.params?.arguments ?? {}))) };
  }
  throw new Error(`Unsupported method: ${req.method}`);
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on("line", (line) => {
  if (!line.trim()) return;
  try {
    const response = handle(JSON.parse(line));
    if (response) send(response);
  } catch (error) {
    send({ jsonrpc: "2.0", id: null, error: { code: -32000, message: String(error.message || error) } });
  }
});
