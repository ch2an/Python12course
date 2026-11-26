from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]
COURSE_COLORS = [
    "#DCEBFA",
    "#DFF2E1",
    "#FCE8D5",
    "#F5DDF0",
    "#FFF2C6",
    "#D9F0EF",
    "#E6E0F8",
    "#F8DEDE",
]
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
DAY_START_MINUTES = 8 * 60
DAY_END_MINUTES = 23 * 60


def default_week_one_monday(semester):
    """用學期年份和上下學期估算預設週一；使用者仍應依校曆核對。"""
    if len(str(semester)) == 4 and str(semester)[:3].isdigit():
        year = int(str(semester)[:3]) + 1911
        month = 9 if str(semester)[-1] == "1" else 2
        first_day = date(year, month, 1)
        return first_day + timedelta(days=(-first_day.weekday()) % 7)
    today = date.today()
    return today - timedelta(days=today.weekday())


def dates_for_week(week_one_monday, week_number):
    if week_one_monday.weekday() != 0:
        raise ValueError("第 1 週的起始日期必須是星期一。")
    if not isinstance(week_number, int) or week_number < 1:
        raise ValueError("週次必須是大於零的整數。")
    monday = week_one_monday + timedelta(days=(week_number - 1) * 7)
    return [monday + timedelta(days=offset) for offset in range(7)]


def valid_calendar_color(color):
    if not isinstance(color, str) or len(color) != 7 or color[0] != "#":
        return False
    try:
        int(color[1:], 16)
        return True
    except ValueError:
        return False


def default_course_color(offering_id):
    course_key = str(offering_id or "")
    color_index = sum(ord(character) for character in course_key) % len(COURSE_COLORS)
    return COURSE_COLORS[color_index]


def event_color(event):
    color = event.get("color")
    if valid_calendar_color(color):
        return color
    return default_course_color(event.get("offering_id") or event.get("id"))


def _time_minutes(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    hour, minute = value[:2], value[3:]
    if not hour.isdigit() or not minute.isdigit():
        return None
    hour = int(hour)
    minute = int(minute)
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _load_font(size):
    for path in FONT_PATHS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise OSError("找不到支援中文的字型，無法輸出課表照片。")


def _wrap_text(draw, text, font, max_width):
    lines = []
    current_line = ""
    for character in str(text):
        candidate = current_line + character
        if current_line and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current_line)
            current_line = character
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)
    return lines


def _dark_text_color(background):
    red = int(background[1:3], 16)
    green = int(background[3:5], 16)
    blue = int(background[5:7], 16)
    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "#222222" if brightness > 145 else "#FFFFFF"


def render_calendar_png(events, semester, week_number, week_dates):
    """將一週課表輸出為含日期、週次與課程顏色的 PNG。"""
    if len(week_dates) != 7:
        raise ValueError("課表圖片需要完整一週的七個日期。")

    image_width = 1680
    time_column_width = 112
    margin = 24
    header_height = 142
    row_height = 68
    row_count = (DAY_END_MINUTES - DAY_START_MINUTES) // 60
    image_height = header_height + row_count * row_height + 32
    day_column_width = (image_width - margin * 2 - time_column_width) // 7
    grid_left = margin + time_column_width
    grid_top = header_height
    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(30)
    heading_font = _load_font(18)
    body_font = _load_font(16)
    small_font = _load_font(13)

    draw.text(
        (margin, 20),
        str(semester) + "｜第 " + str(week_number) + " 週課表",
        fill="#1F2937",
        font=title_font,
    )
    date_range = (
        week_dates[0].strftime("%Y/%m/%d")
        + " - "
        + week_dates[-1].strftime("%Y/%m/%d")
    )
    draw.text((margin, 70), date_range, fill="#4B5563", font=heading_font)

    for day_index, (day_name, current_date) in enumerate(zip(DAY_NAMES, week_dates)):
        x1 = grid_left + day_index * day_column_width
        x2 = x1 + day_column_width
        draw.rectangle(
            (x1, 104, x2, grid_top),
            fill="#EEF2F7",
            outline="#CBD5E1",
            width=1,
        )
        draw.text(
            (x1 + 8, 108),
            "星期" + day_name,
            fill="#1F2937",
            font=heading_font,
        )
        draw.text(
            (x1 + 8, 130),
            current_date.strftime("%Y/%m/%d"),
            fill="#475569",
            font=small_font,
        )

    event_lanes = {day_name: [] for day_name in DAY_NAMES}
    for event in events:
        day_name = event.get("day")
        start = _time_minutes(event.get("start"))
        end = _time_minutes(event.get("end"))
        if (
            day_name not in event_lanes
            or start is None
            or end is None
            or start >= end
            or end <= DAY_START_MINUTES
            or start >= DAY_END_MINUTES
        ):
            continue
        event_lanes[day_name].append({
            "event": event,
            "start": max(start, DAY_START_MINUTES),
            "end": min(end, DAY_END_MINUTES),
        })

    for hour_index in range(row_count):
        y1 = grid_top + hour_index * row_height
        y2 = y1 + row_height
        hour = DAY_START_MINUTES + hour_index * 60
        draw.rectangle(
            (margin, y1, grid_left, y2),
            fill="#F8FAFC",
            outline="#CBD5E1",
            width=1,
        )
        draw.text(
            (margin + 16, y1 + 22),
            str(hour // 60).zfill(2) + ":00",
            fill="#334155",
            font=body_font,
        )
        for day_index in range(7):
            x1 = grid_left + day_index * day_column_width
            draw.rectangle(
                (x1, y1, x1 + day_column_width, y2),
                fill="white",
                outline="#CBD5E1",
                width=1,
            )

    for day_index, day_name in enumerate(DAY_NAMES):
        day_events = sorted(
            event_lanes[day_name],
            key=lambda item: (item["start"], item["end"]),
        )
        lane_ends = []
        for item in day_events:
            lane_index = next(
                (
                    index
                    for index, lane_end in enumerate(lane_ends)
                    if lane_end <= item["start"]
                ),
                len(lane_ends),
            )
            if lane_index == len(lane_ends):
                lane_ends.append(item["end"])
            else:
                lane_ends[lane_index] = item["end"]
            item["lane"] = lane_index
        lane_count = max(len(lane_ends), 1)
        day_left = grid_left + day_index * day_column_width
        lane_width = day_column_width / lane_count

        for item in day_events:
            event = item["event"]
            left = int(day_left + item["lane"] * lane_width + 3)
            right = int(day_left + (item["lane"] + 1) * lane_width - 3)
            top = int(
                grid_top
                + (item["start"] - DAY_START_MINUTES) * row_height / 60
                + 3
            )
            bottom = int(
                grid_top
                + (item["end"] - DAY_START_MINUTES) * row_height / 60
                - 3
            )
            background = event_color(event)
            text_color = _dark_text_color(background)
            draw.rounded_rectangle(
                (left, top, right, max(bottom, top + 20)),
                radius=7,
                fill=background,
                outline="#94A3B8",
                width=1,
            )
            text_left = left + 6
            max_text_width = max(right - left - 12, 16)
            lines = _wrap_text(
                draw,
                event.get("title", "未命名課程"),
                body_font,
                max_text_width,
            )
            current_y = top + 6
            for line in lines[:2]:
                draw.text(
                    (text_left, current_y),
                    line,
                    fill=text_color,
                    font=body_font,
                )
                current_y += 20
            if bottom - top >= 46:
                time_text = (
                    str(event.get("start", ""))
                    + "-"
                    + str(event.get("end", ""))
                )
                draw.text(
                    (text_left, min(current_y + 2, bottom - 18)),
                    time_text,
                    fill=text_color,
                    font=small_font,
                )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
