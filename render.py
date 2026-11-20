#!/usr/bin/env python3
"""Vẽ dashboard lịch + todo cho Kindle Paperwhite 11th gen (1236x1648, xám).

Dữ liệu thật (dùng trong GitHub Actions):
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN  (biến môi trường)
    python render.py --out _site/dashboard.png

Xem trước bằng dữ liệu mẫu:
    python render.py --sample sample.json --out preview.png
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- cấu hình
# Điểm ảnh thật của màn Kindle. Paperwhite 3/4 (300ppi 6"): 1072x1448 · PW5/Oasis: 1236x1648
PW = int(os.environ.get("DASH_PW", "1236"))
PH = int(os.environ.get("DASH_PH", "1648"))
# Phóng to toàn bộ bố cục (chữ + khoảng cách). 1.0 = cỡ gốc, 1.3 = to hơn 30%.
SCALE = float(os.environ.get("DASH_SCALE", "1.3"))
# Hướng màn hình (biến DASH_ORIENT): doc = dọc (mặc định) · ngang = vẽ ngang 1448x1072 rồi xoay 90° (cổng sạc bên trái)
ORIENT = (os.environ.get("DASH_ORIENT") or "doc").strip().lower()
CW, CH = (PH, PW) if ORIENT == "ngang" else (PW, PH)   # kích thước khung vẽ thật
W, H = round(CW / SCALE), round(CH / SCALE)   # kích thước "logic" dùng khi bố trí
TZ = ZoneInfo(os.environ.get("DASH_TZ", "Asia/Ho_Chi_Minh"))
# Bỏ qua các lịch có tên trong danh sách này (phân tách bằng dấu phẩy)
# Bố cục (biến DASH_LAYOUT): lich = ngày + thời tiết ở đầu (mặc định) · claude = bỏ đầu trang, mục Claude to ở trên cùng
TITLE = os.environ.get("DASH_TITLE") or "Claude"   # tiêu đề bố cục "claude"
LAYOUT = (os.environ.get("DASH_LAYOUT") or "lich").strip().lower()
SKIP_CALENDARS = {s.strip() for s in os.environ.get("DASH_SKIP_CALENDARS", "").split(",") if s.strip()}

FONT_DIR = Path(__file__).parent / "fonts"
BLACK, DARK, MID, LIGHT, PALE, WHITE = 0, 60, 120, 180, 225, 255
MARGIN = round(72 / SCALE ** 0.5)   # lề tăng ít hơn chữ để không phí chỗ

THU = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (FONT_DIR / f"Inter-{weight}.otf",
              Path(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if weight in ('Bold', 'SemiBold') else ''}.ttf")):
        if p.exists():
            return ImageFont.truetype(str(p), round(size * SCALE))
    return ImageFont.load_default(round(size * SCALE))


class ScaledDraw:
    """Vẽ theo toạ độ logic, tự nhân SCALE sang điểm ảnh thật (chữ vẫn nét căng)."""

    def __init__(self, img):
        self._img = img
        self._d = ImageDraw.Draw(img)

    @staticmethod
    def _xy(v):
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
            return [(x * SCALE, y * SCALE) for x, y in v]
        return [c * SCALE for c in v]

    @staticmethod
    def _kw(kw):
        for k in ("width", "radius"):
            if k in kw:
                kw[k] = max(1, round(kw[k] * SCALE))
        return kw

    def textlength(self, text, font):
        return self._d.textlength(text, font=font) / SCALE

    def text(self, xy, text, **kw):
        self._d.text((xy[0] * SCALE, xy[1] * SCALE), text, **kw)

    def line(self, xy, **kw):
        self._d.line(self._xy(xy), **self._kw(kw))

    def polygon(self, xy, **kw):
        self._d.polygon(self._xy(xy), **self._kw(kw))

    def ellipse(self, xy, **kw):
        self._d.ellipse(self._xy(xy), **self._kw(kw))

    def rounded_rectangle(self, xy, **kw):
        self._d.rounded_rectangle(self._xy(xy), **self._kw(kw))


# ---------------------------------------------------------------- dữ liệu
@dataclass
class Event:
    title: str
    start: datetime | None  # None = cả ngày
    end: datetime | None
    location: str = ""
    calendar: str = ""

    @property
    def all_day(self) -> bool:
        return self.start is None


@dataclass
class Task:
    title: str
    due: date | None
    list_name: str = ""
    notes: str = ""


def _google_session():
    import requests

    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def _get_all(s, url, params=None):
    params = dict(params or {})
    while True:
        r = s.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        yield from data.get("items", [])
        if not data.get("nextPageToken"):
            return
        params["pageToken"] = data["nextPageToken"]


def fetch_google(today: date) -> tuple[list[Event], list[Task]]:
    s = _google_session()
    t0 = datetime.combine(today, time.min, TZ)
    t1 = t0 + timedelta(days=2)

    events: list[Event] = []
    for cal in _get_all(s, "https://www.googleapis.com/calendar/v3/users/me/calendarList"):
        name = cal.get("summaryOverride") or cal.get("summary", "")
        if name in SKIP_CALENDARS or cal.get("selected") is False:
            continue
        for e in _get_all(s, f"https://www.googleapis.com/calendar/v3/calendars/{cal['id']}/events", {
            "timeMin": t0.isoformat(), "timeMax": t1.isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 100,
        }):
            if e.get("status") == "cancelled":
                continue
            if any(a.get("self") and a.get("responseStatus") == "declined" for a in e.get("attendees", [])):
                continue
            st, en = e.get("start", {}), e.get("end", {})
            if "dateTime" in st:
                start = datetime.fromisoformat(st["dateTime"]).astimezone(TZ)
                end = datetime.fromisoformat(en["dateTime"]).astimezone(TZ)
                events.append(Event(e.get("summary", "(Không tiêu đề)"), start, end, e.get("location", ""), name))
            else:
                d0, d1 = date.fromisoformat(st["date"]), date.fromisoformat(en["date"])
                # mỗi ngày của sự kiện cả ngày -> ghi lại ngày bắt đầu bằng end=None, start=None
                for i in range((d1 - d0).days):
                    d = d0 + timedelta(days=i)
                    if today <= d <= today + timedelta(days=1):
                        ev = Event(e.get("summary", "(Không tiêu đề)"), None, None, e.get("location", ""), name)
                        ev.__dict__["day"] = d
                        events.append(ev)

    tasks: list[Task] = []
    for tl in _get_all(s, "https://tasks.googleapis.com/tasks/v1/users/@me/lists"):
        for t in _get_all(s, f"https://tasks.googleapis.com/tasks/v1/lists/{tl['id']}/tasks", {
            "showCompleted": "false", "showHidden": "false", "maxResults": 100,
        }):
            if not t.get("title", "").strip():
                continue
            due = date.fromisoformat(t["due"][:10]) if t.get("due") else None
            tasks.append(Task(t["title"].strip(), due, tl.get("title", ""), t.get("notes", "")))
    return events, tasks


def parse_payload(data: dict, today: date) -> tuple[list[Event], list[Task]]:
    """Đọc JSON từ Google Apps Script (apps_script.gs)."""
    events: list[Event] = []
    for e in data.get("events", []):
        name = e.get("calendar", "")
        if name in SKIP_CALENDARS:
            continue
        if e.get("allDay"):
            d0 = date.fromisoformat(e["startDate"])
            d1 = date.fromisoformat(e.get("endDate") or e["startDate"])
            if d1 <= d0:
                d1 = d0 + timedelta(days=1)
            d = d0
            while d < d1:
                if today <= d <= today + timedelta(days=45):
                    ev = Event(e["title"], None, None, e.get("location", ""), name)
                    ev.__dict__["day"] = d
                    events.append(ev)
                d += timedelta(days=1)
        else:
            start = datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(TZ)
            end = datetime.fromisoformat(e["end"].replace("Z", "+00:00")).astimezone(TZ)
            events.append(Event(e["title"], start, end, e.get("location", ""), name))
    tasks = [Task(t["title"], date.fromisoformat(t["due"]) if t.get("due") else None,
                  t.get("list", ""), t.get("notes", "")) for t in data.get("tasks", [])]
    return events, tasks


def fetch_appscript(url: str, today: date) -> tuple[list[Event], list[Task]]:
    import requests

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise SystemExit(f"Apps Script báo lỗi: {data['error']} (kiểm tra token trong DATA_URL)")
    global CLAUDE_USAGE, KINDLE
    CLAUDE_USAGE = data.get("claude")
    KINDLE = data.get("kindle")
    if CLAUDE_USAGE:
        fb = _find_fable(CLAUDE_USAGE)
        print("Fable:", f"{fb.get('utilization')}%" if fb else "không thấy trong số liệu")
    return parse_payload(data, today)


# ---------------------------------------------------------------- mức dùng Claude
KINDLE: dict | None = None         # {"battery": 60, "at": "..."} do Kindle gửi lên
CLAUDE_USAGE: dict | None = None   # {"five_hour": {"utilization", "resets_at"}, "seven_day": {...}, "fetched_at"}
THU_NGAN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _reset_label(iso: str | None, now: datetime) -> str:
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return ""
    if t.date() == now.date():
        return f"đặt lại {t:%H:%M}"
    return f"đặt lại {THU_NGAN[t.weekday()]} {t:%H:%M}"


def draw_claude(d, y: int, usage: dict, now: datetime, x0=None, x1=None) -> int:
    """Hai thanh: phiên 5 giờ + giới hạn tuần. Trả về y mới."""
    L = MARGIN if x0 is None else x0
    R = W - MARGIN if x1 is None else x1
    f_lab, f_pct, f_small = font("Bold", 24), font("Bold", 30), font("Regular", 22)
    d.text((L, y), "CLAUDE", font=f_lab, fill=BLACK)
    fetched = usage.get("fetched_at")
    if fetched:
        try:
            ft = datetime.fromisoformat(fetched.replace("Z", "+00:00")).astimezone(TZ)
            age = (now - ft).total_seconds() / 3600
            if age > 2:
                note = f"số liệu cũ, lúc {ft:%H:%M %d/%m}"
                d.text((R - d.textlength(note, font=f_small), y + 2), note, font=f_small, fill=MID)
        except ValueError:
            pass
    y += 38
    gap = 40
    col_w = (R - L - gap) / 2
    for i, (key, name) in enumerate((("five_hour", "Phiên hiện tại"), ("seven_day", "Tuần này"))):
        x0 = L + i * (col_w + gap)
        v = (usage.get(key) or {})
        pct = v.get("utilization")
        pct_txt = "--" if pct is None else f"{round(pct)}%"
        d.text((x0, y), name, font=font("Medium", 24), fill=DARK)
        d.text((x0 + col_w - d.textlength(pct_txt, font=f_pct), y - 4), pct_txt, font=f_pct, fill=BLACK)
        by = y + 38
        d.rounded_rectangle([x0, by, x0 + col_w, by + 16], radius=8, outline=BLACK, width=2)
        if pct:
            fill_w = max(16, col_w * min(pct, 100) / 100)
            d.rounded_rectangle([x0, by, x0 + fill_w, by + 16], radius=8, fill=BLACK)
        d.text((x0, by + 24), _reset_label(v.get("resets_at"), now), font=f_small, fill=MID)
    return y + 92


def _remaining(iso: str | None, now: datetime) -> tuple[str, datetime | None]:
    """→ ("còn 2 giờ 05 phút", thời điểm đặt lại)"""
    if not iso:
        return "", None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return "", None
    mins = max(0, int((t - now).total_seconds() // 60))
    days, rem = divmod(mins, 1440)
    hrs, m = divmod(rem, 60)
    if days:
        txt = f"còn {days} ngày {hrs} giờ"
    elif hrs:
        txt = f"còn {hrs} giờ {m:02d} phút"
    else:
        txt = f"còn {m} phút"
    return txt, t


def draw_claude_big(d, y: int, usage: dict | None, now: datetime) -> int:
    """Bố cục claude: Tuần này 1 khối rất to (số % gấp đôi) + hàng nhỏ Phiên 5 giờ | Fable."""
    # dòng tiêu đề: [logo.png nếu có trong repo] + TITLE
    x = MARGIN
    logo_path = next((p for p in Path(__file__).parent.iterdir() if p.name.lower() == "logo.png"), None)
    if logo_path:
        try:
            lg = Image.open(logo_path).convert("RGBA")
            lh = round(52 * SCALE)
            lg = lg.resize((max(1, round(lg.width * lh / lg.height)), lh), Image.LANCZOS)
            bg = Image.new("RGBA", lg.size, (255, 255, 255, 255))
            bg.alpha_composite(lg)
            d._img.paste(bg.convert("L"), (round(x * SCALE), round((y - 4) * SCALE)))
            x += lg.width / SCALE + 16
        except Exception as e:
            print("Không đọc được logo.png:", e)
    d.text((x, y + 22), TITLE, font=font("Bold", 42), fill=BLACK, anchor="lm")
    note, stale = "", False
    if usage and usage.get("fetched_at"):
        try:
            ft = datetime.fromisoformat(usage["fetched_at"].replace("Z", "+00:00")).astimezone(TZ)
            stale = (now - ft).total_seconds() > 7200
            note = (f"SỐ LIỆU CŨ · {ft:%H:%M %d/%m}" if stale else f"số liệu lúc {ft:%H:%M}")
        except ValueError:
            pass
    if note:
        fn = font("SemiBold" if stale else "Regular", 24)
        d.text((W - MARGIN - d.textlength(note, font=fn), y + 22), note, font=fn, fill=BLACK if stale else MID, anchor="lm")
    y += 12
    y += 48
    d.line([(MARGIN, y), (W - MARGIN, y)], fill=BLACK, width=6)
    y += 26
    if not usage:
        d.text((MARGIN, y), "Chưa có số liệu từ Mac mini.", font=font("Regular", 32), fill=MID)
        return y + 70

    week = usage.get("seven_day") or {}
    y = _claude_block(d, y, "Tuần này", week, now, timedelta(days=7), big=True)
    y += 4
    # hàng nhỏ 2 cột: Phiên 5 giờ | Fable
    gap = 44
    col_w = (W - 2 * MARGIN - gap) / 2
    fable = _find_fable(usage)
    _claude_mini(d, MARGIN, y, col_w, "Phiên 5 giờ", usage.get("five_hour") or {}, now)
    _claude_mini(d, MARGIN + col_w + gap, y, col_w, "Fable", fable, now,
                 empty="chưa có số liệu Fable")
    return y + 140


def _find_fable(usage: dict) -> dict | None:
    """Tìm mức dùng Fable. API đặt nó trong danh sách "limits" (kind weekly_scoped,
    scope.model.display_name = "Fable"); Apps Script gửi kèm bản thô trong trường "raw"."""
    key = os.environ.get("DASH_FABLE_KEY", "").strip()
    if key and isinstance(usage.get(key), dict):
        return usage[key]
    limits = usage.get("limits")
    if limits is None and usage.get("raw"):
        try:
            limits = json.loads(usage["raw"]).get("limits")
        except (ValueError, AttributeError):
            limits = None
    for lim in limits or []:
        if not isinstance(lim, dict):
            continue
        scope = lim.get("scope") or {}
        name = ((scope.get("model") or {}).get("display_name") or "") if isinstance(scope, dict) else ""
        if "fable" in name.lower():
            return {"utilization": lim.get("percent"), "resets_at": lim.get("resets_at")}
    for k, v in usage.items():
        if isinstance(v, dict) and ("fable" in k.lower() or "mythos" in k.lower()):
            return v
    return None


def _pct_text(d, x, y, pct, fp):
    """Vẽ số % với các chữ số rộng bằng nhau (thẳng cột). y = tâm dọc."""
    pct_txt = "--" if pct is None else f"{round(pct):02d}%"
    cell = max(d.textlength(c, font=fp) for c in "0123456789")
    for c in pct_txt:
        cw = d.textlength(c, font=fp)
        if c.isdigit():
            d.text((x + (cell - cw) / 2, y), c, font=fp, fill=BLACK, anchor="lm")
            x += cell
        else:
            d.text((x, y), c, font=fp, fill=BLACK, anchor="lm")
            x += cw
    return x


def _status(pct):
    return ("Thoải mái" if pct < 50 else "Vừa phải" if pct < 80
            else "Sắp chạm giới hạn" if pct < 100 else "Đã hết, chờ đặt lại")


def _claude_block(d, y, name, v, now, span, big=False):
    """Khối to: số % rất to (gấp đôi) bên trái; bên phải tên + trạng thái + đặt lại; dưới là thanh dày toàn chiều ngang."""
    pct = v.get("utilization")
    left, reset_at = _remaining(v.get("resets_at"), now)
    elapsed = min(max(1 - (reset_at - now) / span, 0), 1) if reset_at else None
    fp = font("Bold", 208)
    x_end = _pct_text(d, MARGIN - 8, y + 84, pct, fp)
    rx = x_end + 34
    d.text((rx, y + 14), name.upper(), font=font("Bold", 34), fill=BLACK)
    if pct is not None:
        status = _status(pct)
        fs = font("SemiBold", 32)
        if pct >= 80:   # cảnh báo: chữ trắng trên nền đen
            sw = d.textlength(status, font=fs)
            d.rounded_rectangle([rx, y + 60, rx + sw + 32, y + 106], radius=23, fill=BLACK)
            d.text((rx + 16, y + 83), status, font=fs, fill=WHITE, anchor="lm")
        else:
            d.text((rx, y + 83), status, font=fs, fill=DARK, anchor="lm")
    fi = font("Medium", 26)
    if reset_at:
        when = f"{reset_at:%H:%M}" if reset_at.date() == now.date() else f"{THU_NGAN[reset_at.weekday()]} {reset_at:%H:%M}"
        d.text((rx, y + 124), f"đặt lại {when}", font=fi, fill=DARK, anchor="lm")
        d.text((rx, y + 158), left, font=fi, fill=DARK, anchor="lm")
    y += 182
    # thanh dày toàn chiều ngang
    bx0, bx1 = MARGIN, W - MARGIN
    bar_w = bx1 - bx0
    bh = 50
    d.rounded_rectangle([bx0, y, bx1, y + bh], radius=bh // 2, outline=BLACK, width=5)
    for q in (0.25, 0.5, 0.75):
        x = bx0 + bar_w * q
        d.line([(x, y + 13), (x, y + bh - 13)], fill=LIGHT, width=3)
    if pct:
        fw = max(bh, bar_w * min(pct, 100) / 100)
        d.rounded_rectangle([bx0, y, bx0 + fw, y + bh], radius=bh // 2, fill=BLACK)
    ty = y + bh + 6
    if elapsed is not None:   # ▲ thời gian đã trôi: phần đen nằm trái ▲ = đang dùng chậm hơn thời gian
        mx = bx0 + bar_w * elapsed
        d.polygon([(mx, ty), (mx - 13, ty + 18), (mx + 13, ty + 18)], fill=BLACK)
        cap = f"đã trôi {round(elapsed * 100)}% thời gian"
        fc = font("Regular", 22)
        cw = d.textlength(cap, font=fc)
        cx = mx + 20 if mx + 20 + cw <= bx1 else mx - 20 - cw
        d.text((cx, ty - 1), cap, font=fc, fill=MID)
    return ty + 34


def _claude_mini(d, x0, y, w, name, v, now, empty=""):
    """Khối nhỏ trong 1 cột: tên + % · thanh mỏng · đặt lại."""
    v = v or {}
    pct = v.get("utilization")
    d.text((x0, y), name, font=font("SemiBold", 30), fill=DARK)
    fp = font("Bold", 44)
    pct_txt = "--" if pct is None else f"{round(pct)}%"
    d.text((x0 + w - d.textlength(pct_txt, font=fp), y - 8), pct_txt, font=fp, fill=BLACK)
    by, bh = y + 50, 22
    d.rounded_rectangle([x0, by, x0 + w, by + bh], radius=bh // 2, outline=BLACK, width=3)
    if pct:
        fw = max(bh, w * min(pct, 100) / 100)
        d.rounded_rectangle([x0, by, x0 + fw, by + bh], radius=bh // 2, fill=BLACK)
    left, reset_at = _remaining(v.get("resets_at"), now)
    if reset_at:
        when = f"{reset_at:%H:%M}" if reset_at.date() == now.date() else f"{THU_NGAN[reset_at.weekday()]} {reset_at:%H:%M}"
        cap = f"đặt lại {when} · {left}"
    else:
        cap = empty if pct is None else ""
    fc = font("Regular", 22)
    d.text((x0, by + bh + 10), fit(d, cap, fc, w), font=fc, fill=MID)


def load_sample(path: str, today: date) -> tuple[list[Event], list[Task]]:
    """Mẫu JSON: giờ dạng "HH:MM" tính theo hôm nay, "+1 HH:MM" là ngày mai; due là số ngày lệch."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def parse(v):
        off = 0
        if v.startswith("+"):
            o, v = v.split(" ", 1)
            off = int(o)
        hh, mm = map(int, v.split(":"))
        return datetime.combine(today + timedelta(days=off), time(hh, mm), TZ)

    events = []
    for e in data.get("events", []):
        if "day" in e:
            ev = Event(e["title"], None, None, e.get("location", ""))
            ev.__dict__["day"] = today + timedelta(days=e["day"])
        else:
            ev = Event(e["title"], parse(e["start"]), parse(e["end"]), e.get("location", ""))
        events.append(ev)
    tasks = [Task(t["title"], today + timedelta(days=t["due"]) if t.get("due") is not None else None,
                  t.get("list", "")) for t in data.get("tasks", [])]
    return events, tasks


def event_day(e: Event) -> date:
    return e.__dict__.get("day") if e.all_day else e.start.date()


# ---------------------------------------------------------------- vẽ
def fit(d: ImageDraw.ImageDraw, text: str, f, max_w: int) -> str:
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(d, text, f, max_w, max_lines=2):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(d, lines[-1] + " …", f, max_w)
    return [fit(d, l, f, max_w) for l in lines]


# ---------------------------------------------------------------- thời tiết
LAT = float(os.environ.get("DASH_LAT", "21.0285"))   # mặc định: Hà Nội — đặt DASH_LAT/DASH_LON cho thành phố của bạn
LON = float(os.environ.get("DASH_LON", "105.8542"))

WMO = {0: ("Trời quang", "sun"), 1: ("Nắng nhẹ", "sun"), 2: ("Có mây", "partly"), 3: ("Nhiều mây", "cloud"),
       45: ("Sương mù", "fog"), 48: ("Sương mù", "fog"), 51: ("Mưa phùn", "rain"), 53: ("Mưa phùn", "rain"),
       55: ("Mưa phùn", "rain"), 61: ("Mưa nhỏ", "rain"), 63: ("Mưa vừa", "rain"), 65: ("Mưa to", "rain"),
       80: ("Mưa rào", "rain"), 81: ("Mưa rào", "rain"), 82: ("Mưa rất to", "rain"),
       95: ("Dông", "storm"), 96: ("Dông, mưa đá", "storm"), 99: ("Dông, mưa đá", "storm")}


@dataclass
class Weather:
    temp: float
    code: int
    tmin: float
    tmax: float
    rain: int            # % khả năng mưa
    aqi: int | None = None

    @property
    def desc(self):
        return WMO.get(self.code, ("", "cloud"))[0]

    @property
    def icon(self):
        return WMO.get(self.code, ("", "cloud"))[1]


MET_SYMBOL = [("thunder", 95), ("heavyrain", 65), ("rainshowers", 80), ("lightrain", 61), ("drizzle", 51),
              ("rain", 63), ("sleet", 63), ("snow", 63), ("fog", 45), ("partlycloudy", 2), ("fair", 1),
              ("clearsky", 0), ("cloudy", 3)]


def _get_json(url, params, headers=None, tries=3):
    """GET JSON, thử lại vài lần (Open-Meteo đôi khi chặn/giới hạn IP của GitHub Actions)."""
    import time
    import requests
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers or {}, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(3 * (i + 1))
    raise last


def _weather_openmeteo() -> Weather:
    r = _get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": LAT, "longitude": LON, "timezone": str(TZ), "forecast_days": 1,
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    return Weather(r["current"]["temperature_2m"], r["current"]["weather_code"],
                   r["daily"]["temperature_2m_min"][0], r["daily"]["temperature_2m_max"][0],
                   r["daily"]["precipitation_probability_max"][0] or 0)


def _weather_met() -> Weather:
    """Dự phòng: MET Norway (api.met.no), miễn phí, không cần khoá."""
    r = _get_json("https://api.met.no/weatherapi/locationforecast/2.0/complete",
                  {"lat": round(LAT, 4), "lon": round(LON, 4)},
                  headers={"User-Agent": "kindle-dashboard github.com/tranvinhcopsn-maker/kindle-dashboard"})
    ts = r["properties"]["timeseries"]
    temps = [t["data"]["instant"]["details"]["air_temperature"] for t in ts[:24]]
    sym = ""
    for t in ts[:3]:
        sym = (t["data"].get("next_1_hours") or t["data"].get("next_6_hours") or {}).get("summary", {}).get("symbol_code", "")
        if sym:
            break
    code = next((c for k, c in MET_SYMBOL if k in sym), 3)
    probs = [(t["data"].get("next_1_hours") or {}).get("details", {}).get("probability_of_precipitation")
             for t in ts[:12]]
    probs = [p for p in probs if p is not None]
    return Weather(temps[0], code, min(temps), max(temps), min(100, round(max(probs))) if probs else 0)


def fetch_weather() -> Weather | None:
    w = None
    for name, fn in (("Open-Meteo", _weather_openmeteo), ("MET Norway", _weather_met)):
        try:
            w = fn()
            print("Thời tiết lấy từ", name)
            break
        except Exception as e:  # thời tiết lỗi thì vẫn vẽ phần còn lại
            print(f"Không lấy được thời tiết từ {name}:", e)
    if w is None:
        return None
    try:
        a = _get_json("https://air-quality-api.open-meteo.com/v1/air-quality",
                      {"latitude": LAT, "longitude": LON, "current": "us_aqi"}, tries=2)
        w.aqi = round(a["current"]["us_aqi"])
    except Exception:
        pass
    return w


def aqi_label(v):
    for lim, name in ((50, "Tốt"), (100, "Trung bình"), (150, "Kém"), (200, "Xấu"), (300, "Rất xấu")):
        if v <= lim:
            return name
    return "Nguy hại"


def draw_icon(d, kind, cx, cy, s):
    """Icon thời tiết đơn giản, nét đen, hợp e-ink. s = bán kính cơ sở."""
    import math

    def sun(x, y, r):
        d.ellipse([x - r, y - r, x + r, y + r], outline=BLACK, width=6)
        for i in range(8):
            a = i * math.pi / 4
            d.line([(x + math.cos(a) * r * 1.45, y + math.sin(a) * r * 1.45),
                    (x + math.cos(a) * r * 1.9, y + math.sin(a) * r * 1.9)], fill=BLACK, width=6)

    def cloud(x, y, w, fill=WHITE):
        h = w * 0.55
        parts = [(x - w * .30, y + h * .05, w * .28), (x + w * .02, y - h * .25, w * .34), (x + w * .32, y + h * .08, w * .24)]
        for px, py, r in parts:  # viền
            d.ellipse([px - r - 6, py - r - 6, px + r + 6, py + r + 6], fill=BLACK)
        d.rounded_rectangle([x - w * .58 - 6, y - 6, x + w * .56 + 6, y + h * .45 + 6], radius=int(h * .3), fill=BLACK)
        for px, py, r in parts:
            d.ellipse([px - r, py - r, px + r, py + r], fill=fill)
        d.rounded_rectangle([x - w * .58, y, x + w * .56, y + h * .45], radius=int(h * .3), fill=fill)

    if kind == "sun":
        sun(cx, cy, s * .55)
    elif kind == "partly":
        sun(cx + s * .35, cy - s * .35, s * .42)
        cloud(cx - s * .1, cy + s * .1, s * 1.5)
    elif kind in ("cloud", "fog"):
        cloud(cx, cy - s * .1, s * 1.7)
        if kind == "fog":
            for i in range(3):
                d.line([(cx - s * .8, cy + s * .55 + i * 16), (cx + s * .8, cy + s * .55 + i * 16)], fill=BLACK, width=6)
    else:  # rain / storm
        cloud(cx, cy - s * .3, s * 1.7)
        if kind == "storm":
            d.polygon([(cx, cy + s * .25), (cx - s * .25, cy + s * .75), (cx, cy + s * .7),
                       (cx - s * .15, cy + s * 1.1), (cx + s * .3, cy + s * .55), (cx + s * .05, cy + s * .58)], fill=BLACK)
        else:
            for i in (-1, 0, 1):
                x = cx + i * s * .45
                d.line([(x + 8, cy + s * .35), (x - 8, cy + s * .8)], fill=BLACK, width=7)


# ---------------------------------------------------------------- vẽ
def section_title(d, y, text, right="", x0=None, x1=None):
    x0 = MARGIN if x0 is None else x0
    x1 = W - MARGIN if x1 is None else x1
    f = font("Bold", 28)
    d.text((x0, y), text.upper(), font=f, fill=BLACK)
    if right:
        fr = font("Medium", 26)
        d.text((x1 - d.textlength(right, font=fr), y + 2), right, font=fr, fill=MID)
    d.line([(x0, y + 44), (x1, y + 44)], fill=BLACK, width=3)
    return y + 62


def hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def due_tag(t: Task, today: date):
    if not t.due:
        return ""
    if t.due < today:
        return "Quá hạn"
    if t.due == today:
        return "Hôm nay"
    if t.due == today + timedelta(days=1):
        return "Ngày mai"
    return f"{t.due.day}/{t.due.month}"


def render(events: list[Event], tasks: list[Task], now: datetime, weather: Weather | None = None) -> Image.Image:
    from lunar import solar_to_lunar, year_name

    today, tomorrow = now.date(), now.date() + timedelta(days=1)
    img = Image.new("L", (CW, CH), WHITE)
    d = ScaledDraw(img)
    f_sub = font("Regular", 28)

    if LAYOUT == "claude":
        # ============ BỐ CỤC CLAUDE: không có đầu trang, Claude to ở trên cùng
        y = draw_claude_big(d, 40, CLAUDE_USAGE, now)
        d.line([(MARGIN, y - 20), (W - MARGIN, y - 20)], fill=PALE, width=2)
        y += 14
    else:
        # ============ HEADER: ngày + âm lịch | thời tiết
        y = 56
        d.text((MARGIN, y), THU[today.weekday()], font=font("Bold", 88), fill=BLACK)
        d.text((MARGIN, y + 112), f"{today.day} tháng {today.month}, {today.year}", font=font("SemiBold", 38), fill=DARK)
        ld, lm, ly, leap = solar_to_lunar(today.day, today.month, today.year)
        lunar_txt = f"Âm lịch {ld}/{lm}{' nhuận' if leap else ''} · năm {year_name(ly)}"
        d.text((MARGIN, y + 164), lunar_txt, font=f_sub, fill=MID)

        if weather:
            right = W - MARGIN
            ft = font("Bold", 96)
            t = f"{round(weather.temp)}°"
            tw = d.textlength(t, font=ft)
            d.text((right - tw, y - 6), t, font=ft, fill=BLACK)
            draw_icon(d, weather.icon, int(right - tw - 85), y + 52, 62)
            l1 = f"{weather.desc} · {round(weather.tmin)}–{round(weather.tmax)}°"
            l2 = f"Mưa {weather.rain}%" + (f" · AQI {weather.aqi} {aqi_label(weather.aqi)}" if weather.aqi is not None else "")
            fw = font("Medium", 28)
            d.text((right - d.textlength(l1, font=fw), y + 124), l1, font=fw, fill=DARK)
            d.text((right - d.textlength(l2, font=f_sub), y + 164), l2, font=f_sub, fill=MID)
        y += 222
        d.line([(MARGIN, y), (W - MARGIN, y)], fill=BLACK, width=6)
        y += 32

        # ============ MỨC DÙNG CLAUDE (nếu Mac mini có gửi số liệu)
        if CLAUDE_USAGE:
            y = draw_claude(d, y, CLAUDE_USAGE, now)
            d.line([(MARGIN, y), (W - MARGIN, y)], fill=PALE, width=2)
            y += 28

    ev_today = sorted([e for e in events if event_day(e) == today], key=lambda e: (not e.all_day, e.start or now))
    ev_tom = sorted([e for e in events if event_day(e) == tomorrow], key=lambda e: (not e.all_day, e.start or now))
    timed = [e for e in ev_today if not e.all_day]
    nxt = next((e for e in timed if e.end > now), None)

    # ============ THẺ "TIẾP THEO" (nền đen, nổi bật trên e-ink)
    if nxt:
        live = nxt.start <= now
        has_loc = bool(nxt.location)
        ch = 150 if has_loc else 118
        d.rounded_rectangle([MARGIN, y, W - MARGIN, y + ch], radius=18, fill=BLACK)
        label = ("ĐANG DIỄN RA" if live else "TIẾP THEO") + f" · {hm(nxt.start)}–{hm(nxt.end)}"
        d.text((MARGIN + 32, y + 18), label, font=font("SemiBold", 26), fill=PALE)
        d.text((MARGIN + 32, y + 52), fit(d, nxt.title, font("Bold", 44), W - 2 * MARGIN - 64),
               font=font("Bold", 44), fill=WHITE)
        if has_loc:
            d.text((MARGIN + 32, y + 106), fit(d, "@ " + nxt.location, f_sub, W - 2 * MARGIN - 64), font=f_sub, fill=PALE)
        y += ch + 34

    # ---- tính trước khối dưới cùng (lịch hôm nay + ngày mai) để todo lấp phần giữa
    footer_y = H - 64
    min_todo = 62 + 3 * 72 if tasks else 140   # luôn chừa chỗ cho ít nhất ~3 việc
    cal_max, tom_max = 6, 3

    def _bottom_h(cm, tm):
        cr = min(len(ev_today), cm) or 1
        tr = min(len(ev_tom), tm) or 1
        return (62 + 46 * cr + (36 if len(ev_today) > cm else 0) + 26) + (62 + 44 * tr) + 16

    # thiếu chỗ cho todo → bớt dòng lịch (ngày mai trước, rồi hôm nay)
    while footer_y - _bottom_h(cal_max, tom_max) - y < min_todo and (tom_max > 1 or cal_max > 1):
        if tom_max > 1:
            tom_max -= 1
        else:
            cal_max -= 1
    bottom_y = footer_y - _bottom_h(cal_max, tom_max)

    # ============ VIỆC CẦN LÀM (khu vực chính)
    tasks_open = sorted(tasks, key=lambda t: (t.due is None, t.due or date.max, t.title.lower()))
    overdue = sum(1 for t in tasks_open if t.due and t.due < today)
    due_today = sum(1 for t in tasks_open if t.due == today)
    right = f"{len(tasks_open)} việc" + (f" · {overdue} quá hạn" if overdue else "") + \
        (f" · {due_today} hôm nay" if due_today else "")
    y = section_title(d, y, "Việc cần làm", right if tasks_open else "")
    f_task, box = font("Medium", 32), 36   # mỗi việc đúng 1 dòng, dài thì cắt "…"
    if not tasks_open:
        d.text((MARGIN, y + 6), "Không còn việc nào. Tuyệt vời!", font=font("Regular", 36), fill=MID)
        y += 70
    for i, t in enumerate(tasks_open):
        tag = due_tag(t, today)
        f_tag = font("SemiBold", 22)
        tag_w = int(d.textlength(tag, font=f_tag)) + 28 if tag else 0
        text_w = W - 2 * MARGIN - box - 24 - (tag_w + 20 if tag else 0)
        line = fit(d, t.title, f_task, text_w)
        limit = bottom_y - (16 if i == len(tasks_open) - 1 else 44)  # chừa chỗ cho "+ N việc nữa"
        row_h = 66
        if y + row_h > limit:
            d.text((MARGIN, y + 4), f"+ {len(tasks_open) - i} việc nữa", font=f_sub, fill=MID)
            y += 44
            break
        d.rounded_rectangle([MARGIN, y + 4, MARGIN + box, y + 4 + box], radius=8, outline=BLACK, width=4)
        d.text((MARGIN + box + 24, y + 22), line, font=f_task, fill=BLACK, anchor="lm")
        if tag:
            x1, x0 = W - MARGIN, W - MARGIN - tag_w
            if tag in ("Quá hạn", "Hôm nay"):
                d.rounded_rectangle([x0, y + 4, x1, y + 40], radius=18, fill=BLACK)
                d.text(((x0 + x1) / 2, y + 22), tag, font=f_tag, fill=WHITE, anchor="mm")
            else:
                d.rounded_rectangle([x0, y + 4, x1, y + 40], radius=18, outline=MID, width=2)
                d.text(((x0 + x1) / 2, y + 22), tag, font=f_tag, fill=DARK, anchor="mm")
        y += row_h
        d.line([(MARGIN + box + 28, y - 8), (W - MARGIN, y - 8)], fill=PALE, width=2)
        y += 6

    # ============ LỊCH HÔM NAY (gọn, ghim phía dưới)
    y = bottom_y
    y = section_title(d, y, "Lịch hôm nay", f"{len(ev_today)} sự kiện" if ev_today else "")
    time_w = 250
    f_ev, f_evb = font("Regular", 32), font("SemiBold", 32)
    if not ev_today:
        d.text((MARGIN, y), "Không có sự kiện nào.", font=f_ev, fill=MID)
        y += 46
    shown = list(ev_today)
    while len(shown) > cal_max:   # thiếu chỗ: bỏ sự kiện đã qua trước, rồi tới cuối danh sách
        past_i = next((k for k, x in enumerate(shown) if not x.all_day and x.end <= now), None)
        shown.pop(past_i if past_i is not None else -1)
    for i, e in enumerate(shown):
        past = (not e.all_day) and e.end <= now
        is_next = e is nxt
        col = LIGHT if past else BLACK
        tf = f_evb if is_next else f_ev
        when = "Cả ngày" if e.all_day else f"{hm(e.start)}–{hm(e.end)}"
        d.text((MARGIN, y), when, font=font("Medium", 28), fill=LIGHT if past else DARK)
        d.text((MARGIN + time_w, y - 2), fit(d, e.title, tf, W - 2 * MARGIN - time_w), font=tf, fill=col)
        if past:  # gạch ngang sự kiện đã qua
            tw = min(d.textlength(fit(d, e.title, tf, W - 2 * MARGIN - time_w), font=tf), W - 2 * MARGIN - time_w)
            d.line([(MARGIN + time_w, y + 20), (MARGIN + time_w + tw, y + 20)], fill=LIGHT, width=2)
        y += 46
    if len(ev_today) > len(shown):
        d.text((MARGIN, y), f"+ {len(ev_today) - len(shown)} sự kiện khác", font=f_sub, fill=MID)
        y += 36
    y += 26

    # ============ NGÀY MAI
    y = section_title(d, y, "Ngày mai · " + THU[tomorrow.weekday()],
                      f"{len(ev_tom)} sự kiện" if len(ev_tom) > tom_max else "")
    if not ev_tom:
        d.text((MARGIN, y), "Chưa có lịch.", font=f_ev, fill=MID)
    for e in ev_tom[:tom_max]:
        d.text((MARGIN, y), "Cả ngày" if e.all_day else hm(e.start), font=font("Medium", 28), fill=DARK)
        d.text((MARGIN + time_w, y - 2), fit(d, e.title, f_ev, W - 2 * MARGIN - time_w), font=f_ev, fill=DARK)
        y += 44

    # ============ FOOTER
    d.line([(MARGIN, footer_y), (W - MARGIN, footer_y)], fill=LIGHT, width=2)
    d.text((MARGIN, footer_y + 16), (f"{THU[today.weekday()]} {today.day}/{today.month} · " if LAYOUT == "claude" else "") + f"Cập nhật {now.strftime('%H:%M %d/%m')}", font=font("Regular", 24), fill=MID)
    draw_battery(d, footer_y + 16, now)
    return img


def battery_text(now: datetime) -> str:
    """'Pin 60%' từ số liệu Kindle gửi lên (bỏ qua nếu cũ hơn 3 giờ)."""
    k = KINDLE or {}
    b = k.get("battery")
    if b is None:
        return ""
    try:
        at = datetime.fromisoformat(str(k.get("at")).replace("Z", "+00:00")).astimezone(TZ)
        if (now - at).total_seconds() > 3 * 3600:
            return ""
    except ValueError:
        pass
    return f"Pin {round(float(b))}%"


def draw_battery(d, y, now, x1=None):
    t = battery_text(now)
    if not t:
        return
    x1 = W - MARGIN if x1 is None else x1
    f = font("Medium", 24)
    low = KINDLE and float(KINDLE.get("battery", 100)) < 20
    tw = d.textlength(t, font=f)
    if low:   # pin yếu: chữ trắng nền đen
        d.rounded_rectangle([x1 - tw - 24, y - 4, x1, y + 30], radius=17, fill=BLACK)
        d.text((x1 - tw - 12, y), t, font=f, fill=WHITE)
    else:
        # vẽ biểu tượng pin nhỏ trước chữ
        bx1 = x1 - tw - 12
        bx0 = bx1 - 34
        d.rounded_rectangle([bx0, y + 6, bx1 - 4, y + 24], radius=3, outline=MID, width=2)
        d.line([(bx1 - 2, y + 11), (bx1 - 2, y + 19)], fill=MID, width=3)
        lvl = max(0.0, min(1.0, float(KINDLE["battery"]) / 100))
        if lvl > 0:
            d.rounded_rectangle([bx0 + 4, y + 10, bx0 + 4 + (bx1 - bx0 - 12) * lvl, y + 20], radius=1, fill=MID)
        d.text((x1 - tw, y), t, font=f, fill=MID)


def draw_claude_header(d, y, x0, x1, usage, now):
    """Đầu trang bố cục ngang: 2 khối Claude (Phiên hiện tại | Tuần này), chỉ số % to + giờ đặt lại."""
    usage = usage or {}
    stale = False
    if usage.get("fetched_at"):
        try:
            ft = datetime.fromisoformat(usage["fetched_at"].replace("Z", "+00:00")).astimezone(TZ)
            stale = (now - ft).total_seconds() > 7200
        except ValueError:
            pass
    gap = 40
    cw = (x1 - x0 - gap) / 2
    f_lab, f_pct, f_rs = font("Bold", 24), font("Bold", 96), font("Medium", 26)
    for i, (key, name) in enumerate((("five_hour", "Phiên hiện tại"), ("seven_day", "Tuần này"))):
        cx = x0 + i * (cw + gap)
        v = usage.get(key) or {}
        pct = v.get("utilization")
        d.text((cx, y), ("CLAUDE · " if i == 0 else "") + name.upper(), font=f_lab, fill=DARK)
        if i == 1 and stale:
            d.text((cx + d.textlength(name.upper(), font=f_lab) + 14, y), "(SỐ LIỆU CŨ)", font=f_lab, fill=BLACK)
        d.text((cx - 4, y + 28), "--" if pct is None else f"{round(pct)}%", font=f_pct, fill=BLACK)
        left, reset_at = _remaining(v.get("resets_at"), now)
        if reset_at:
            when = f"{reset_at:%H:%M}" if reset_at.date() == now.date() else f"{THU_NGAN[reset_at.weekday()]} {reset_at:%H:%M}"
            d.text((cx, y + 138), fit(d, f"đặt lại {when}", f_rs, cw), font=f_rs, fill=MID)
    if x1 - x0 > 0:
        mx = x0 + cw + gap / 2
        d.line([(mx, y + 8), (mx, y + 164)], fill=PALE, width=2)


def draw_month(d, y, x0, x1, today, marked, y_max=None) -> int:
    """Lịch cả tháng, tuần bắt đầu thứ Hai. Mỗi ô: ngày dương (to) + ngày âm (nhỏ). Hôm nay: ô đen. Có sự kiện: chấm dưới."""
    import calendar
    from lunar import solar_to_lunar
    f_head = font("Bold", 28)
    d.text((x0, y), f"THÁNG {today.month}/{today.year}", font=f_head, fill=BLACK)
    ld, lm, _, _ = solar_to_lunar(today.day, today.month, today.year)
    note = f"Âm lịch tháng {lm}"
    fr = font("Medium", 24)
    d.text((x1 - d.textlength(note, font=fr), y + 2), note, font=fr, fill=MID)
    y += 44
    d.line([(x0, y), (x1, y)], fill=BLACK, width=3)
    y += 10
    cell_w = (x1 - x0) / 7
    fw = font("SemiBold", 20)
    for i, n in enumerate(["T2", "T3", "T4", "T5", "T6", "T7", "CN"]):
        cx = x0 + cell_w * (i + 0.5)
        d.text((cx, y + 12), n, font=fw, fill=DARK if i < 6 else BLACK, anchor="mm")
    y += 30
    weeks = calendar.Calendar(0).monthdatescalendar(today.year, today.month)
    row_h = 56 if y_max is None else max(56, min(96, (y_max - y) / len(weeks)))
    big = row_h >= 70
    f_day, f_lun = font("SemiBold", 32 if big else 26), font("Regular", 19 if big else 16)
    for wk in weeks:
        for i, dt in enumerate(wk):
            cx = x0 + cell_w * (i + 0.5)
            cy = y + row_h / 2
            other = dt.month != today.month
            is_today = dt == today
            if is_today:
                d.rounded_rectangle([cx - cell_w / 2 + 4, y + 2, cx + cell_w / 2 - 4, y + row_h - 2], radius=10, fill=BLACK)
            col = WHITE if is_today else (PALE if other else (BLACK if dt >= today else MID))
            d.text((cx, cy - 10), str(dt.day), font=f_day, fill=col, anchor="mm")
            ldd, lmm, _, _ = solar_to_lunar(dt.day, dt.month, dt.year)
            lt = f"{ldd}/{lmm}" if ldd == 1 else str(ldd)
            d.text((cx, cy + (20 if big else 15)), lt, font=f_lun, fill=(PALE if is_today else (PALE if other else MID)), anchor="mm")
            if dt in marked and not other:
                r = 4
                dx = cx + cell_w / 2 - 14
                d.ellipse([dx - r, y + 10 - r, dx + r, y + 10 + r], fill=WHITE if is_today else BLACK)
        y += row_h
    return y


# ---------------------------------------------------------------- bố cục ngang
def render_landscape(events, tasks, now, weather) -> Image.Image:
    """Màn ngang 1448x1072: đầu trang (ngày | thời tiết) + 2 cột (Claude & việc | lịch). Trả về ảnh đã xoay 90° cho Kindle."""
    from lunar import solar_to_lunar, year_name

    today, tomorrow = now.date(), now.date() + timedelta(days=1)
    img = Image.new("L", (CW, CH), WHITE)
    d = ScaledDraw(img)
    f_sub = font("Regular", 28)

    # ---- đầu trang: trái = mức dùng Claude (số % to + giờ đặt lại) · phải = thời tiết
    y = 30
    wx0 = W - MARGIN   # mép trái của khối thời tiết
    if weather:
        right = W - MARGIN
        ft = font("Bold", 80)
        t = f"{round(weather.temp)}°"
        tw = d.textlength(t, font=ft)
        d.text((right - tw, y + 4), t, font=ft, fill=BLACK)
        draw_icon(d, weather.icon, int(right - tw - 66), y + 54, 48)
        r2 = f"{weather.desc} {round(weather.tmin)}–{round(weather.tmax)}°"
        r3 = f"Mưa {weather.rain}%" + (f" · AQI {weather.aqi}" if weather.aqi is not None else "")
        fw = font("Medium", 26)
        d.text((right - d.textlength(r2, font=fw), y + 106), r2, font=fw, fill=DARK)
        d.text((right - d.textlength(r3, font=font("Regular", 24)), y + 140), r3, font=font("Regular", 24), fill=MID)
        wx0 = right - max(tw + 140, d.textlength(r2, font=fw), d.textlength(r3, font=font("Regular", 24)))
    draw_claude_header(d, y, MARGIN, wx0 - 50, CLAUDE_USAGE, now)
    y += 190
    d.line([(MARGIN, y), (W - MARGIN, y)], fill=BLACK, width=6)
    y += 28
    top = y

    footer_y = H - 56
    gap = 56
    col = (W - 2 * MARGIN - gap) / 2
    Lx0, Lx1 = MARGIN, MARGIN + col
    Rx0, Rx1 = MARGIN + col + gap, W - MARGIN
    d.line([((Lx1 + Rx0) / 2, top + 4), ((Lx1 + Rx0) / 2, footer_y - 20)], fill=PALE, width=2)

    # ---- cột trái: việc cần làm + sắp tới
    y = top
    tasks_open = sorted(tasks, key=lambda t: (t.due is None, t.due or date.max, t.title.lower()))
    overdue = sum(1 for t in tasks_open if t.due and t.due < today)
    right = f"{len(tasks_open)} việc" + (f" · {overdue} quá hạn" if overdue else "")
    y = section_title(d, y, "Việc cần làm", right if tasks_open else "", Lx0, Lx1)
    f_task, box = font("Medium", 30), 32
    if not tasks_open:
        d.text((Lx0, y + 6), "Không còn việc nào!", font=font("Regular", 32), fill=MID)
    up_reserve = 62 + 3 * 40 + 46 + 24 if events else 0   # chừa chỗ cho mục "Sắp tới" (ít nhất 3 dòng)
    task_end = footer_y - up_reserve
    for i, t in enumerate(tasks_open):
        if y + 60 > task_end - (12 if i == len(tasks_open) - 1 else 50):
            d.text((Lx0, y + 4), f"+ {len(tasks_open) - i} việc nữa", font=f_sub, fill=MID)
            y += 40
            break
        tag = due_tag(t, today)
        f_tag = font("SemiBold", 20)
        tag_w = int(d.textlength(tag, font=f_tag)) + 24 if tag else 0
        d.rounded_rectangle([Lx0, y + 4, Lx0 + box, y + 4 + box], radius=7, outline=BLACK, width=4)
        tx_w = Lx1 - Lx0 - box - 20 - (tag_w + 16 if tag else 0)
        d.text((Lx0 + box + 20, y + 20), fit(d, t.title, f_task, tx_w), font=f_task, fill=BLACK, anchor="lm")
        if tag:
            x1, x0 = Lx1, Lx1 - tag_w
            if tag in ("Quá hạn", "Hôm nay"):
                d.rounded_rectangle([x0, y + 4, x1, y + 36], radius=16, fill=BLACK)
                d.text(((x0 + x1) / 2, y + 20), tag, font=f_tag, fill=WHITE, anchor="mm")
            else:
                d.rounded_rectangle([x0, y + 4, x1, y + 36], radius=16, outline=MID, width=2)
                d.text(((x0 + x1) / 2, y + 20), tag, font=f_tag, fill=DARK, anchor="mm")
        y += 58
        d.line([(Lx0 + box + 24, y - 6), (Lx1, y - 6)], fill=PALE, width=2)
        y += 4

    # ---- cột trái (tiếp): lịch sắp tới
    upcoming = sorted([e for e in events if (event_day(e) > today) or (e.all_day and event_day(e) == today)
                       or (not e.all_day and e.end > now)],
                      key=lambda e: (event_day(e), not e.all_day, e.start or now))
    if upcoming:
        y += 24
        y = section_title(d, y, "Sắp tới", f"{len(upcoming)} sự kiện", Lx0, Lx1)
        f_ev, f_dt = font("Regular", 28), font("Medium", 24)
        date_w = 196
        for i, e in enumerate(upcoming):
            if y + 40 > footer_y - (12 if i == len(upcoming) - 1 else 46):
                d.text((Lx0, y), f"+ {len(upcoming) - i} sự kiện khác", font=font("Regular", 24), fill=MID)
                break
            ed = event_day(e)
            day_lbl = "Hôm nay" if ed == today else "Ngày mai" if ed == today + timedelta(days=1) \
                else f"{THU_NGAN[ed.weekday()]} {ed.day}/{ed.month}"
            when = day_lbl + ("" if e.all_day else f" {hm(e.start)}")
            d.text((Lx0, y + 2), when, font=f_dt, fill=DARK)
            live = (not e.all_day) and e.start <= now
            d.text((Lx0 + date_w, y), fit(d, ("● " if live else "") + e.title, f_ev, Lx1 - Lx0 - date_w), font=f_ev, fill=BLACK)
            y += 40

    # ---- cột phải: lịch cả tháng (kèm âm lịch), chấm = ngày có lịch
    draw_month(d, top, Rx0, Rx1, today, {event_day(e) for e in events}, footer_y - 24)

    # ---- chân trang
    d.line([(MARGIN, footer_y), (W - MARGIN, footer_y)], fill=LIGHT, width=2)
    d.text((MARGIN, footer_y + 14), f"Cập nhật {now.strftime('%H:%M %d/%m')}", font=font("Regular", 24), fill=MID)
    draw_battery(d, footer_y + 14, now)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site/dashboard.png")
    ap.add_argument("--sample", help="file JSON dữ liệu mẫu (không gọi Google)")
    ap.add_argument("--layout", help="lich | claude (mặc định lấy từ DASH_LAYOUT)")
    ap.add_argument("--now", help="giả lập thời điểm, vd 2026-11-03T10:30")
    ap.add_argument("--preview", help="(bố cục ngang) lưu thêm ảnh chưa xoay để xem trước")
    args = ap.parse_args()

    global LAYOUT
    if args.layout:
        LAYOUT = args.layout.strip().lower()
    now = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else datetime.now(TZ)
    if args.sample:
        events, tasks = load_sample(args.sample, now.date())
        sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        w = sample.get("weather")
        weather = Weather(**w) if w else None
        global CLAUDE_USAGE, KINDLE
        CLAUDE_USAGE = sample.get("claude")
        KINDLE = sample.get("kindle")
    else:
        if os.environ.get("DATA_URL"):
            events, tasks = fetch_appscript(os.environ["DATA_URL"], now.date())
        else:
            events, tasks = fetch_google(now.date())
        weather = fetch_weather()
    if ORIENT == "ngang":
        img = render_landscape(events, tasks, now, weather)
        if args.preview:
            img.save(args.preview, optimize=True)
        img = img.transpose(Image.ROTATE_90)   # xoay ngược chiều kim đồng hồ: cổng sạc nằm bên trái
    else:
        img = render(events, tasks, now, weather)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(f"Đã lưu {out} ({len(events)} sự kiện, {len(tasks)} việc, thời tiết: {'có' if weather else 'không'})")


if __name__ == "__main__":
    main()
