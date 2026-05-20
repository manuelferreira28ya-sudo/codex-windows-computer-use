import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from ctypes import wintypes


USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32
USER32.GetForegroundWindow.restype = wintypes.HWND
USER32.GetClipboardData.restype = wintypes.HANDLE
USER32.GetClipboardData.argtypes = [wintypes.UINT]
USER32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
KERNEL32.GlobalAlloc.restype = wintypes.HGLOBAL
KERNEL32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
KERNEL32.GlobalLock.restype = ctypes.c_void_p
KERNEL32.GlobalLock.argtypes = [wintypes.HGLOBAL]
KERNEL32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class INPUT(ctypes.Structure):
    pass


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


INPUT._fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
WM_CLOSE = 0x0010


VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "win": 0x5B,
    "cmd": 0x5B,
}
for i in range(10):
    VK[str(i)] = ord(str(i))
for code in range(ord("a"), ord("z") + 1):
    VK[chr(code)] = code - 32
for i in range(1, 25):
    VK[f"f{i}"] = 0x70 + i - 1


def send_json(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell_json(script):
    encoded = base64_utf16le(script)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "PowerShell UI Automation failed")
    output = completed.stdout.strip()
    if not output:
        return None
    return json.loads(output)


def base64_utf16le(text):
    import base64

    return base64.b64encode(text.encode("utf-16le")).decode("ascii")


def screen_size():
    return USER32.GetSystemMetrics(0), USER32.GetSystemMetrics(1)


def window_info(hwnd):
    length = USER32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(hwnd, title, length + 1)
    rect = RECT()
    USER32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {"hwnd": int(hwnd), "title": title.value, "rect": [rect.left, rect.top, rect.right, rect.bottom]}


def visible_windows():
    windows = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not USER32.IsWindowVisible(hwnd):
            return True
        length = USER32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, title, length + 1)
        rect = RECT()
        USER32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return True
        info = {"hwnd": int(hwnd), "title": title.value, "rect": [rect.left, rect.top, rect.right, rect.bottom]}
        info["active"] = int(USER32.GetForegroundWindow()) == int(hwnd)
        windows.append(info)
        return True

    USER32.EnumWindows(enum_proc(callback), 0)
    return windows


def mouse_input(flags, mouse_data=0):
    extra = ctypes.pointer(ctypes.c_ulong(0))
    inp = INPUT(type=INPUT_MOUSE, union=INPUTUNION(mi=MOUSEINPUT(0, 0, mouse_data, flags, 0, extra)))
    USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def mouse_event(flags):
    mouse_input(flags)


def key_event(vk, up=False):
    extra = ctypes.pointer(ctypes.c_ulong(0))
    flags = KEYEVENTF_KEYUP if up else 0
    inp = INPUT(type=INPUT_KEYBOARD, union=INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, extra)))
    USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def unicode_char(ch):
    extra = ctypes.pointer(ctypes.c_ulong(0))
    code = ord(ch)
    down = INPUT(type=INPUT_KEYBOARD, union=INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, extra)))
    up = INPUT(type=INPUT_KEYBOARD, union=INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, extra)))
    USER32.SendInput(1, ctypes.byref(down), ctypes.sizeof(down))
    USER32.SendInput(1, ctypes.byref(up), ctypes.sizeof(up))


def set_clipboard_text(text):
    data = (text + "\0").encode("utf-16le")
    if not USER32.OpenClipboard(None):
        raise OSError("Could not open clipboard")
    try:
        USER32.EmptyClipboard()
        handle = KERNEL32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("GlobalAlloc failed")
        locked = KERNEL32.GlobalLock(handle)
        if not locked:
            raise OSError("GlobalLock failed")
        ctypes.memmove(locked, data, len(data))
        KERNEL32.GlobalUnlock(handle)
        if not USER32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("SetClipboardData failed")
    finally:
        USER32.CloseClipboard()


def get_clipboard_text():
    if not USER32.OpenClipboard(None):
        raise OSError("Could not open clipboard")
    try:
        handle = USER32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = KERNEL32.GlobalLock(handle)
        if not locked:
            raise OSError("GlobalLock failed")
        try:
            return ctypes.wstring_at(locked)
        finally:
            KERNEL32.GlobalUnlock(handle)
    finally:
        USER32.CloseClipboard()


def key_code(name):
    value = str(name).lower().strip()
    if value not in VK:
        raise ValueError(f"Unsupported key: {name}")
    return VK[value]


def tool_screenshot(args):
    try:
        from PIL import ImageGrab
    except Exception as exc:
        return text_result(f"Screenshot requires Pillow. Install with: python -m pip install pillow. Error: {exc}")
    out_dir = args.get("directory") or os.path.join(tempfile.gettempdir(), "windows-computer-use")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"screenshot-{uuid.uuid4().hex}.png")
    all_screens = bool(args.get("all_screens", True))
    bbox = args.get("bbox")
    if bbox:
        img = ImageGrab.grab(bbox=tuple(int(v) for v in bbox), all_screens=all_screens)
    else:
        img = ImageGrab.grab(all_screens=all_screens)
    img.save(path)
    return text_result(json.dumps({"path": path, "size": img.size, "all_screens": all_screens, "bbox": bbox}))


def screenshot_payload(args):
    return json.loads(tool_screenshot(args)["content"][0]["text"])


def tool_screenshot_region(args):
    bbox = [int(args["x"]), int(args["y"]), int(args["x"]) + int(args["width"]), int(args["y"]) + int(args["height"])]
    return tool_screenshot({**args, "bbox": bbox, "all_screens": bool(args.get("all_screens", True))})


def tool_list_windows(args):
    query = str(args.get("query", "")).lower().strip()
    limit = int(args.get("limit", 30))
    rows = visible_windows()
    if query:
        rows = [w for w in rows if query in w["title"].lower()]
    return text_result(json.dumps(rows[:limit]))


def tool_active_window(_args):
    hwnd = USER32.GetForegroundWindow()
    if not hwnd:
        return text_result(json.dumps(None))
    return text_result(json.dumps(window_info(hwnd)))


def tool_focus_window(args):
    query = str(args["query"]).lower().strip()
    exact = bool(args.get("exact", False))
    exclude = [str(item).lower() for item in args.get("exclude", [])]
    windows = [w for w in visible_windows() if not any(item in w["title"].lower() for item in exclude)]
    if exact:
        matches = [w for w in windows if query == w["title"].lower().strip()]
    else:
        matches = [w for w in windows if query in w["title"].lower()]
    if not matches:
        raise ValueError(f"No visible window title contains: {args['query']}")
    hwnd = matches[0]["hwnd"]
    return tool_focus_window_handle({"hwnd": hwnd})


def tool_focus_window_handle(args):
    hwnd = int(args["hwnd"])
    USER32.ShowWindow(hwnd, 9)
    time.sleep(float(args.get("delay_seconds", 0.05)))
    USER32.SetForegroundWindow(hwnd)
    info = window_info(hwnd)
    return text_result(json.dumps({"focused": info["title"], "hwnd": hwnd, "rect": info["rect"]}))


def tool_minimize_window_handle(args):
    hwnd = int(args["hwnd"])
    USER32.ShowWindow(hwnd, 6)
    return text_result(json.dumps({"minimized": hwnd}))


def tool_restore_window_handle(args):
    hwnd = int(args["hwnd"])
    USER32.ShowWindow(hwnd, 9)
    USER32.SetForegroundWindow(hwnd)
    return text_result(json.dumps({"restored": hwnd, "window": window_info(hwnd)}))


def tool_wait_for_window(args):
    query = str(args["query"]).lower().strip()
    exact = bool(args.get("exact", False))
    exclude = [str(item).lower() for item in args.get("exclude", [])]
    timeout = float(args.get("timeout_seconds", 10))
    deadline = time.time() + timeout
    while time.time() < deadline:
        windows = [w for w in visible_windows() if not any(item in w["title"].lower() for item in exclude)]
        if exact:
            matches = [w for w in windows if query == w["title"].lower().strip()]
        else:
            matches = [w for w in windows if query in w["title"].lower()]
        if matches:
            return text_result(json.dumps({"match": matches[0]}))
        time.sleep(0.2)
    raise ValueError(f"Timed out waiting for window: {args['query']}")


def tool_mouse_position(_args):
    pt = POINT()
    USER32.GetCursorPos(ctypes.byref(pt))
    return text_result(json.dumps({"x": pt.x, "y": pt.y, "screen_size": screen_size()}))


def mouse_position_payload():
    pt = POINT()
    USER32.GetCursorPos(ctypes.byref(pt))
    return {"x": pt.x, "y": pt.y, "screen_size": screen_size()}


def tool_mouse_move(args):
    USER32.SetCursorPos(int(args["x"]), int(args["y"]))
    return text_result("ok")


def tool_mouse_click(args):
    if "x" in args and "y" in args:
        USER32.SetCursorPos(int(args["x"]), int(args["y"]))
        time.sleep(0.05)
    button = args.get("button", "left").lower()
    flags = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button)
    if not flags:
        raise ValueError("button must be left, right, or middle")
    mouse_event(flags[0])
    time.sleep(float(args.get("hold_seconds", 0.03)))
    mouse_event(flags[1])
    return text_result("ok")


def tool_right_click(args):
    return tool_mouse_click({**args, "button": "right"})


def tool_mouse_double_click(args):
    tool_mouse_click(args)
    time.sleep(0.12)
    tool_mouse_click(args)
    return text_result("ok")


def tool_type_text(args):
    text = args.get("text", "")
    delay = float(args.get("delay_seconds", 0.01))
    for ch in text:
        unicode_char(ch)
        if delay:
            time.sleep(delay)
    return text_result("ok")


def tool_paste_text(args):
    set_clipboard_text(args.get("text", ""))
    time.sleep(float(args.get("before_paste_seconds", 0.05)))
    tool_hotkey({"keys": ["ctrl", "v"]})
    return text_result("ok")


def tool_clipboard_read(_args):
    return text_result(json.dumps({"text": get_clipboard_text()}))


def tool_press_key(args):
    vk = key_code(args["key"])
    key_event(vk, False)
    time.sleep(float(args.get("hold_seconds", 0.03)))
    key_event(vk, True)
    return text_result("ok")


def tool_hotkey(args):
    keys = args.get("keys", [])
    if isinstance(keys, str):
        keys = [part.strip() for part in keys.split(",") if part.strip()]
    codes = [key_code(k) for k in keys]
    for code in codes:
        key_event(code, False)
        time.sleep(0.02)
    for code in reversed(codes):
        key_event(code, True)
        time.sleep(0.02)
    return text_result("ok")


def tool_wait(args):
    time.sleep(float(args.get("seconds", 1)))
    return text_result("ok")


def tool_scroll(args):
    if "x" in args and "y" in args:
        USER32.SetCursorPos(int(args["x"]), int(args["y"]))
        time.sleep(0.03)
    clicks = int(args.get("clicks", args.get("amount", 1)))
    mouse_input(MOUSEEVENTF_WHEEL, int(clicks * 120))
    return text_result("ok")


def tool_drag(args):
    start_x = int(args["start_x"])
    start_y = int(args["start_y"])
    end_x = int(args["end_x"])
    end_y = int(args["end_y"])
    duration = max(0.01, float(args.get("duration_seconds", 0.4)))
    steps = max(2, int(args.get("steps", 20)))
    USER32.SetCursorPos(start_x, start_y)
    time.sleep(0.05)
    mouse_event(MOUSEEVENTF_LEFTDOWN)
    for i in range(1, steps + 1):
        t = i / steps
        x = int(start_x + (end_x - start_x) * t)
        y = int(start_y + (end_y - start_y) * t)
        USER32.SetCursorPos(x, y)
        time.sleep(duration / steps)
    mouse_event(MOUSEEVENTF_LEFTUP)
    return text_result("ok")


def tool_open_app(args):
    target = args["name"]
    try:
        os.startfile(target)
    except OSError:
        subprocess.Popen(target, shell=True)
    return text_result(json.dumps({"opened": target}))


def tool_switch_app(args):
    wait_args = {
        "query": args["query"],
        "exact": args.get("exact", False),
        "exclude": args.get("exclude", []),
        "timeout_seconds": args.get("timeout_seconds", 5),
    }
    match = json.loads(tool_wait_for_window(wait_args)["content"][0]["text"])["match"]
    return tool_focus_window_handle({"hwnd": match["hwnd"]})


def tool_close_window(args):
    if not bool(args.get("confirm", False)):
        raise ValueError("close_window requires confirm=true from an explicit user request")
    hwnd = int(args["hwnd"])
    USER32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return text_result(json.dumps({"close_requested": hwnd}))


def ocr_image(args):
    try:
        import pytesseract
        from PIL import ImageGrab
    except Exception as exc:
        raise RuntimeError(
            "OCR requires Pillow, pytesseract, and the Tesseract OCR app. "
            "Install Python package with `python -m pip install pillow pytesseract` "
            "and install Tesseract for Windows. "
            f"Import error: {exc}"
        )
    tesseract_path = args.get("tesseract_path") or os.environ.get("TESSERACT_CMD") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    bbox = args.get("bbox")
    if bbox:
        img = ImageGrab.grab(bbox=tuple(int(v) for v in bbox), all_screens=bool(args.get("all_screens", True)))
    else:
        img = ImageGrab.grab(all_screens=bool(args.get("all_screens", False)))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data.get("text", [])):
        text = text.strip()
        if not text:
            continue
        conf_raw = data.get("conf", ["-1"])[i]
        try:
            conf = float(conf_raw)
        except ValueError:
            conf = -1
        left = int(data["left"][i]) + (int(bbox[0]) if bbox else 0)
        top = int(data["top"][i]) + (int(bbox[1]) if bbox else 0)
        width = int(data["width"][i])
        height = int(data["height"][i])
        words.append({"text": text, "confidence": conf, "rect": [left, top, left + width, top + height]})
    return words


def tool_ocr_screen(args):
    words = ocr_image(args)
    return text_result(json.dumps({"words": words[: int(args.get("limit", 200))]}))


def find_text_match(args):
    query = str(args["text"]).lower()
    words = ocr_image(args)
    joined = " ".join(w["text"] for w in words).lower()
    if query not in joined:
        return None, words
    for word in words:
        if query in word["text"].lower():
            return word, words
    parts = query.split()
    for i in range(0, max(0, len(words) - len(parts) + 1)):
        candidate = " ".join(w["text"].lower() for w in words[i : i + len(parts)])
        if query in candidate:
            rects = [w["rect"] for w in words[i : i + len(parts)]]
            return {
                "text": " ".join(w["text"] for w in words[i : i + len(parts)]),
                "confidence": min(w["confidence"] for w in words[i : i + len(parts)]),
                "rect": [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)],
            }, words
    return None, words


def tool_find_text(args):
    match, _words = find_text_match(args)
    return text_result(json.dumps({"match": match}))


def tool_wait_for_text(args):
    timeout = float(args.get("timeout_seconds", 10))
    deadline = time.time() + timeout
    while time.time() < deadline:
        match, _words = find_text_match(args)
        if match:
            return text_result(json.dumps({"match": match}))
        time.sleep(float(args.get("poll_seconds", 0.5)))
    raise ValueError(f"Timed out waiting for text: {args['text']}")


def tool_click_text(args):
    match, _words = find_text_match(args)
    if not match:
        raise ValueError(f"Text not found: {args['text']}")
    rect = match["rect"]
    x = int((rect[0] + rect[2]) / 2)
    y = int((rect[1] + rect[3]) / 2)
    tool_mouse_click({"x": x, "y": y, "button": args.get("button", "left")})
    return text_result(json.dumps({"clicked": match, "x": x, "y": y}))


def tool_list_controls(args):
    query = ps_string(args.get("window_query", ""))
    limit = int(args.get("limit", 80))
    script = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$query = {query}.ToLower()
$root = [System.Windows.Automation.AutomationElement]::RootElement
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$target = $null
foreach ($w in $windows) {{
  $name = $w.Current.Name
  if ($name -and ($query.Length -eq 0 -or $name.ToLower().Contains($query))) {{ $target = $w; break }}
}}
if ($null -eq $target) {{ @{{ error = "No matching window" }} | ConvertTo-Json -Compress; exit 0 }}
$items = New-Object System.Collections.Generic.List[object]
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($el in $all) {{
  if ($items.Count -ge {limit}) {{ break }}
  $rect = $el.Current.BoundingRectangle
  $name = $el.Current.Name
  $aid = $el.Current.AutomationId
  $ctype = $el.Current.ControlType.ProgrammaticName
  if (($name -or $aid) -and $rect.Width -gt 0 -and $rect.Height -gt 0) {{
    $items.Add([pscustomobject]@{{
      name = $name
      automationId = $aid
      controlType = $ctype
      rect = @([int]$rect.Left, [int]$rect.Top, [int]$rect.Right, [int]$rect.Bottom)
    }})
  }}
}}
[pscustomobject]@{{ window = $target.Current.Name; controls = $items }} | ConvertTo-Json -Depth 4 -Compress
"""
    return text_result(json.dumps(run_powershell_json(script)))


def tool_click_control(args):
    window_query = str(args.get("window_query", ""))
    query = str(args["query"]).lower()
    controls = json.loads(tool_list_controls({"window_query": window_query, "limit": int(args.get("limit", 200))})["content"][0]["text"])
    if controls.get("error"):
        raise ValueError(controls["error"])
    for control in controls.get("controls", []):
        haystack = " ".join(str(control.get(k, "")) for k in ("name", "automationId", "controlType")).lower()
        if query in haystack:
            rect = control["rect"]
            x = int((rect[0] + rect[2]) / 2)
            y = int((rect[1] + rect[3]) / 2)
            tool_mouse_click({"x": x, "y": y, "button": args.get("button", "left")})
            return text_result(json.dumps({"clicked": control, "x": x, "y": y}))
    raise ValueError(f"No control matched: {args['query']}")


def tool_find_control(args):
    window_query = str(args.get("window_query", ""))
    query = str(args["query"]).lower()
    controls = json.loads(tool_list_controls({"window_query": window_query, "limit": int(args.get("limit", 200))})["content"][0]["text"])
    if controls.get("error"):
        raise ValueError(controls["error"])
    for control in controls.get("controls", []):
        haystack = " ".join(str(control.get(k, "")) for k in ("name", "automationId", "controlType")).lower()
        if query in haystack:
            return text_result(json.dumps({"match": control, "window": controls.get("window")}))
    return text_result(json.dumps({"match": None, "window": controls.get("window")}))


def tool_wait_for_control(args):
    timeout = float(args.get("timeout_seconds", 10))
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = json.loads(tool_find_control(args)["content"][0]["text"])
        if result.get("match"):
            return text_result(json.dumps(result))
        time.sleep(float(args.get("poll_seconds", 0.5)))
    raise ValueError(f"Timed out waiting for control: {args['query']}")


def control_powershell_script(window_query, control_query, action, value=""):
    window_query_ps = ps_string(window_query)
    control_query_ps = ps_string(control_query)
    value_ps = ps_string(value)
    return f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$windowQuery = {window_query_ps}.ToLower()
$controlQuery = {control_query_ps}.ToLower()
$value = {value_ps}
$root = [System.Windows.Automation.AutomationElement]::RootElement
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$target = $null
foreach ($w in $windows) {{
  $name = $w.Current.Name
  if ($name -and ($windowQuery.Length -eq 0 -or $name.ToLower().Contains($windowQuery))) {{ $target = $w; break }}
}}
if ($null -eq $target) {{ @{{ error = "No matching window" }} | ConvertTo-Json -Compress; exit 0 }}
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$match = $null
foreach ($el in $all) {{
  $name = $el.Current.Name
  $aid = $el.Current.AutomationId
  $ctype = $el.Current.ControlType.ProgrammaticName
  $haystack = (($name + " " + $aid + " " + $ctype).ToLower())
  if ($haystack.Contains($controlQuery)) {{ $match = $el; break }}
}}
if ($null -eq $match) {{ @{{ error = "No matching control" }} | ConvertTo-Json -Compress; exit 0 }}
$rect = $match.Current.BoundingRectangle
$out = [ordered]@{{
  name = $match.Current.Name
  automationId = $match.Current.AutomationId
  controlType = $match.Current.ControlType.ProgrammaticName
  rect = @([int]$rect.Left, [int]$rect.Top, [int]$rect.Right, [int]$rect.Bottom)
}}
try {{
  if ("{action}" -eq "invoke") {{
    $pattern = $match.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
    $out.action = "invoke"
  }} elseif ("{action}" -eq "set_value") {{
    $pattern = $match.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $pattern.SetValue($value)
    $out.action = "set_value"
  }}
}} catch {{
  $out.error = $_.Exception.Message
}}
$out | ConvertTo-Json -Depth 4 -Compress
"""


def tool_invoke_control(args):
    data = run_powershell_json(control_powershell_script(str(args.get("window_query", "")), str(args["query"]), "invoke"))
    if data and data.get("error"):
        if data["error"] == "No matching control":
            return tool_click_control(args)
        raise ValueError(data["error"])
    if data and data.get("error"):
        return tool_click_control(args)
    return text_result(json.dumps(data))


def tool_set_control_value(args):
    data = run_powershell_json(
        control_powershell_script(str(args.get("window_query", "")), str(args["query"]), "set_value", str(args["text"]))
    )
    if data and data.get("error"):
        fallback = tool_type_into_control({**args, "paste": True})
        return text_result(json.dumps({"uia": data, "fallback": json.loads(fallback["content"][0]["text"])}))
    return text_result(json.dumps(data))


def tool_type_into_control(args):
    click_result = json.loads(tool_click_control(args)["content"][0]["text"])
    if args.get("paste", True):
        tool_paste_text({"text": args["text"]})
    else:
        tool_type_text({"text": args["text"], "delay_seconds": args.get("delay_seconds", 0.01)})
    return text_result(json.dumps({"target": click_result.get("clicked"), "typed": True}))


def observe_payload(args):
    payload = {
        "active_window": json.loads(tool_active_window({})["content"][0]["text"]),
        "mouse": mouse_position_payload(),
    }
    window_limit = int(args.get("window_limit", 12))
    payload["windows"] = visible_windows()[:window_limit]
    if args.get("screenshot", True):
        screenshot_args = {
            "all_screens": bool(args.get("all_screens", False)),
            "directory": args.get("directory"),
        }
        if args.get("bbox"):
            screenshot_args["bbox"] = args["bbox"]
        payload["screenshot"] = screenshot_payload({k: v for k, v in screenshot_args.items() if v is not None})
    if args.get("ocr", False):
        ocr_args = {
            "all_screens": bool(args.get("all_screens", False)),
            "limit": int(args.get("ocr_limit", 80)),
        }
        if args.get("bbox"):
            ocr_args["bbox"] = args["bbox"]
        try:
            payload["ocr"] = json.loads(tool_ocr_screen(ocr_args)["content"][0]["text"])
        except Exception as exc:
            payload["ocr_error"] = str(exc)
    if args.get("controls", False):
        try:
            payload["controls"] = json.loads(
                tool_list_controls(
                    {
                        "window_query": args.get("window_query", payload["active_window"].get("title", "")),
                        "limit": int(args.get("control_limit", 80)),
                    }
                )["content"][0]["text"]
            )
        except Exception as exc:
            payload["controls_error"] = str(exc)
    return payload


def tool_observe(args):
    return text_result(json.dumps(observe_payload(args)))


def run_action(name, action_args):
    if name not in ACTION_TOOLS:
        raise ValueError(f"Unsupported action: {name}")
    return ACTION_TOOLS[name](action_args)


def tool_act(args):
    name = args["tool"]
    result = run_action(name, args.get("arguments") or {})
    return text_result(json.dumps({"tool": name, "result": result.get("content", [])}))


def tool_act_and_observe(args):
    if "actions" in args:
        action_result = tool_batch_actions({"actions": args["actions"]})
    else:
        action_result = tool_act({"tool": args["tool"], "arguments": args.get("arguments") or {}})
    observe_args = args.get("observe") or {}
    if "directory" in args and "directory" not in observe_args:
        observe_args["directory"] = args["directory"]
    return text_result(
        json.dumps(
            {
                "action": json.loads(action_result["content"][0]["text"]),
                "observation": observe_payload(observe_args),
            }
        )
    )


def tool_batch_actions(args):
    actions = args.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("actions must be an array")
    results = []
    for index, action in enumerate(actions):
        name = action.get("tool")
        if name not in ACTION_TOOLS:
            raise ValueError(f"Unsupported batch action at index {index}: {name}")
        action_args = action.get("arguments") or {}
        ACTION_TOOLS[name](action_args)
        results.append({"index": index, "tool": name, "status": "ok"})
        pause = float(action.get("pause_after_seconds", 0))
        if pause:
            time.sleep(pause)
    return text_result(json.dumps({"count": len(results), "results": results}))


ACTION_TOOLS = {
    "mouse_move": tool_mouse_move,
    "mouse_click": tool_mouse_click,
    "mouse_double_click": tool_mouse_double_click,
    "right_click": tool_right_click,
    "drag": tool_drag,
    "scroll": tool_scroll,
    "type_text": tool_type_text,
    "paste_text": tool_paste_text,
    "press_key": tool_press_key,
    "hotkey": tool_hotkey,
    "wait": tool_wait,
    "focus_window": tool_focus_window,
    "focus_window_handle": tool_focus_window_handle,
    "minimize_window_handle": tool_minimize_window_handle,
    "restore_window_handle": tool_restore_window_handle,
    "switch_app": tool_switch_app,
    "click_control": tool_click_control,
    "invoke_control": tool_invoke_control,
    "type_into_control": tool_type_into_control,
    "set_control_value": tool_set_control_value,
}


TOOLS = {
    "observe": {
        "description": "Return a combined desktop observation: active window, mouse, visible windows, optional screenshot, OCR, and UI controls.",
        "inputSchema": {"type": "object", "properties": {"screenshot": {"type": "boolean"}, "all_screens": {"type": "boolean"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "directory": {"type": "string"}, "ocr": {"type": "boolean"}, "ocr_limit": {"type": "integer"}, "controls": {"type": "boolean"}, "window_query": {"type": "string"}, "window_limit": {"type": "integer"}, "control_limit": {"type": "integer"}}, "additionalProperties": False},
        "handler": tool_observe,
    },
    "act": {
        "description": "Run one safe action tool by name. For multiple actions use batch_actions or act_and_observe.",
        "inputSchema": {"type": "object", "properties": {"tool": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["tool"], "additionalProperties": False},
        "handler": tool_act,
    },
    "act_and_observe": {
        "description": "Run one action or a batch of actions, then immediately return a fresh observation.",
        "inputSchema": {"type": "object", "properties": {"tool": {"type": "string"}, "arguments": {"type": "object"}, "actions": {"type": "array", "items": {"type": "object", "properties": {"tool": {"type": "string"}, "arguments": {"type": "object"}, "pause_after_seconds": {"type": "number"}}, "required": ["tool"], "additionalProperties": False}}, "observe": {"type": "object"}, "directory": {"type": "string"}}, "additionalProperties": False},
        "handler": tool_act_and_observe,
    },
    "screenshot": {
        "description": "Capture Windows screens and save a PNG. Use all_screens=false for a faster primary-monitor screenshot.",
        "inputSchema": {"type": "object", "properties": {"directory": {"type": "string"}, "all_screens": {"type": "boolean"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}}, "additionalProperties": False},
        "handler": tool_screenshot,
    },
    "screenshot_region": {
        "description": "Capture a rectangular screen region and save a PNG.",
        "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "directory": {"type": "string"}, "all_screens": {"type": "boolean"}}, "required": ["x", "y", "width", "height"], "additionalProperties": False},
        "handler": tool_screenshot_region,
    },
    "list_windows": {
        "description": "List visible Windows app windows, optionally filtered by title.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False},
        "handler": tool_list_windows,
    },
    "focus_window": {
        "description": "Focus the first visible window whose title contains query. Use exact=true for exact title match or exclude to skip titles.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "exact": {"type": "boolean"}, "exclude": {"type": "array", "items": {"type": "string"}}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_focus_window,
    },
    "active_window": {
        "description": "Return the current foreground window title, hwnd, and rectangle.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": tool_active_window,
    },
    "focus_window_handle": {
        "description": "Restore and focus a window by exact hwnd.",
        "inputSchema": {"type": "object", "properties": {"hwnd": {"type": "integer"}, "delay_seconds": {"type": "number"}}, "required": ["hwnd"], "additionalProperties": False},
        "handler": tool_focus_window_handle,
    },
    "minimize_window_handle": {
        "description": "Minimize a window by exact hwnd.",
        "inputSchema": {"type": "object", "properties": {"hwnd": {"type": "integer"}}, "required": ["hwnd"], "additionalProperties": False},
        "handler": tool_minimize_window_handle,
    },
    "restore_window_handle": {
        "description": "Restore and focus a minimized window by exact hwnd.",
        "inputSchema": {"type": "object", "properties": {"hwnd": {"type": "integer"}}, "required": ["hwnd"], "additionalProperties": False},
        "handler": tool_restore_window_handle,
    },
    "wait_for_window": {
        "description": "Wait until a visible window title appears.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "exact": {"type": "boolean"}, "exclude": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": "number"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_wait_for_window,
    },
    "mouse_position": {
        "description": "Return the current mouse position and screen size.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": tool_mouse_position,
    },
    "mouse_move": {
        "description": "Move the mouse to absolute screen coordinates.",
        "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"], "additionalProperties": False},
        "handler": tool_mouse_move,
    },
    "mouse_click": {
        "description": "Click a mouse button, optionally moving to x/y first.",
        "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string"}, "hold_seconds": {"type": "number"}}, "additionalProperties": False},
        "handler": tool_mouse_click,
    },
    "right_click": {
        "description": "Right-click, optionally moving to x/y first.",
        "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "hold_seconds": {"type": "number"}}, "additionalProperties": False},
        "handler": tool_right_click,
    },
    "mouse_double_click": {
        "description": "Double-click a mouse button, optionally moving to x/y first.",
        "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string"}}, "additionalProperties": False},
        "handler": tool_mouse_double_click,
    },
    "type_text": {
        "description": "Type text into the focused Windows control.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "delay_seconds": {"type": "number"}}, "required": ["text"], "additionalProperties": False},
        "handler": tool_type_text,
    },
    "paste_text": {
        "description": "Put text on the clipboard and paste it into the focused Windows control. Faster than type_text for long text.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "before_paste_seconds": {"type": "number"}}, "required": ["text"], "additionalProperties": False},
        "handler": tool_paste_text,
    },
    "clipboard_read": {
        "description": "Read Unicode text currently on the clipboard.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": tool_clipboard_read,
    },
    "press_key": {
        "description": "Press and release one key.",
        "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "hold_seconds": {"type": "number"}}, "required": ["key"], "additionalProperties": False},
        "handler": tool_press_key,
    },
    "hotkey": {
        "description": "Press a key combination, for example ctrl,l or alt,tab.",
        "inputSchema": {"type": "object", "properties": {"keys": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}}, "required": ["keys"], "additionalProperties": False},
        "handler": tool_hotkey,
    },
    "wait": {
        "description": "Wait for a number of seconds.",
        "inputSchema": {"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"], "additionalProperties": False},
        "handler": tool_wait,
    },
    "scroll": {
        "description": "Scroll at the current mouse position, or move to x/y first. Positive clicks scroll up, negative clicks scroll down.",
        "inputSchema": {"type": "object", "properties": {"clicks": {"type": "integer"}, "amount": {"type": "integer"}, "x": {"type": "integer"}, "y": {"type": "integer"}}, "additionalProperties": False},
        "handler": tool_scroll,
    },
    "drag": {
        "description": "Drag from one screen coordinate to another.",
        "inputSchema": {"type": "object", "properties": {"start_x": {"type": "integer"}, "start_y": {"type": "integer"}, "end_x": {"type": "integer"}, "end_y": {"type": "integer"}, "duration_seconds": {"type": "number"}, "steps": {"type": "integer"}}, "required": ["start_x", "start_y", "end_x", "end_y"], "additionalProperties": False},
        "handler": tool_drag,
    },
    "open_app": {
        "description": "Open an app, executable, document, or URI using Windows shell resolution.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
        "handler": tool_open_app,
    },
    "switch_app": {
        "description": "Wait for a matching window and focus it.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "exact": {"type": "boolean"}, "exclude": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": "number"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_switch_app,
    },
    "close_window": {
        "description": "Request a window close by hwnd. Requires confirm=true after explicit user approval.",
        "inputSchema": {"type": "object", "properties": {"hwnd": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["hwnd", "confirm"], "additionalProperties": False},
        "handler": tool_close_window,
    },
    "batch_actions": {
        "description": "Run multiple non-screenshot actions in one call to reduce latency. Supports window focus/restore/minimize, mouse, keyboard, scroll, drag, controls, wait, and switch_app tools.",
        "inputSchema": {"type": "object", "properties": {"actions": {"type": "array", "items": {"type": "object", "properties": {"tool": {"type": "string"}, "arguments": {"type": "object"}, "pause_after_seconds": {"type": "number"}}, "required": ["tool"], "additionalProperties": False}}}, "required": ["actions"], "additionalProperties": False},
        "handler": tool_batch_actions,
    },
    "ocr_screen": {
        "description": "Run OCR on the primary screen or bbox and return detected words. Requires pytesseract and Tesseract OCR.",
        "inputSchema": {"type": "object", "properties": {"bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "all_screens": {"type": "boolean"}, "limit": {"type": "integer"}}, "additionalProperties": False},
        "handler": tool_ocr_screen,
    },
    "find_text": {
        "description": "Find visible text with OCR and return its rectangle. Requires pytesseract and Tesseract OCR.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "all_screens": {"type": "boolean"}}, "required": ["text"], "additionalProperties": False},
        "handler": tool_find_text,
    },
    "wait_for_text": {
        "description": "Poll OCR until visible text appears. Requires pytesseract and Tesseract OCR.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "all_screens": {"type": "boolean"}, "timeout_seconds": {"type": "number"}, "poll_seconds": {"type": "number"}}, "required": ["text"], "additionalProperties": False},
        "handler": tool_wait_for_text,
    },
    "click_text": {
        "description": "Find visible text with OCR and click its center. Requires pytesseract and Tesseract OCR.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "all_screens": {"type": "boolean"}, "button": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
        "handler": tool_click_text,
    },
    "list_controls": {
        "description": "List named UI Automation controls for a matching Windows app window.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False},
        "handler": tool_list_controls,
    },
    "click_control": {
        "description": "Click a UI Automation control by name, automation id, or control type within a matching window.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "button": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_click_control,
    },
    "find_control": {
        "description": "Find a UI Automation control by name, automation id, or control type within a matching window.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_find_control,
    },
    "wait_for_control": {
        "description": "Poll UI Automation until a matching control appears.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}, "timeout_seconds": {"type": "number"}, "poll_seconds": {"type": "number"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_wait_for_control,
    },
    "invoke_control": {
        "description": "Invoke a UI Automation control by pattern when available; falls back to clicking it.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "button": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"], "additionalProperties": False},
        "handler": tool_invoke_control,
    },
    "type_into_control": {
        "description": "Click a matching UI Automation control and type or paste text into it.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "text": {"type": "string"}, "paste": {"type": "boolean"}, "delay_seconds": {"type": "number"}, "limit": {"type": "integer"}}, "required": ["query", "text"], "additionalProperties": False},
        "handler": tool_type_into_control,
    },
    "set_control_value": {
        "description": "Set a UI Automation ValuePattern control directly when available; falls back to click and paste.",
        "inputSchema": {"type": "object", "properties": {"window_query": {"type": "string"}, "query": {"type": "string"}, "text": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query", "text"], "additionalProperties": False},
        "handler": tool_set_control_value,
    },
}


def handle(req):
    method = req.get("method")
    req_id = req.get("id")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "windows-computer-use", "version": "0.5.1"},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": [{"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]} for name, spec in TOOLS.items()]}
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            if name not in TOOLS:
                raise ValueError(f"Unknown tool: {name}")
            result = TOOLS[name]["handler"](params.get("arguments") or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(exc)}}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            send_json(response)


if __name__ == "__main__":
    main()
