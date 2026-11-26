"""擷取中央大學官方課程查詢頁面的指定學期與開課單位。"""

import argparse
import datetime
from html.parser import HTMLParser
import json
import re
import sys

import requests


BASE_URL = "https://cis.ncu.edu.tw"
QUERY_PATH = "/Course/main/query/byKeywords"
DEPARTMENT_PATH = "/Course/ajax/call/plaincall/CourseSearchService.getUnitSelection.dwr"
DEFAULT_DEPARTMENT = "核心通識課程"
DEFAULT_SEMESTER = "1151"
DEFAULT_DEPARTMENTS = [
    "中國文學系",
    "英美語文學系",
    "法國語文學系",
    "文學院學士班",
    "數學系",
    "物理學系",
    "化學學系",
    "光電科學與工程學系",
    "理學院學士班",
]
GENERAL_EDUCATION_UNITS = ["核心通識課程", "通識教育中心"]
DEFAULT_DEMO_QUERIES = [
    (DEFAULT_SEMESTER, department)
    for department in DEFAULT_DEPARTMENTS
] + [
    (DEFAULT_SEMESTER, department)
    for department in GENERAL_EDUCATION_UNITS
]
FALLBACK_DEPARTMENTS = {
    "1151": DEFAULT_DEPARTMENTS + GENERAL_EDUCATION_UNITS,
}
DAY_NAMES = {
    "Sun": "日",
    "Mon": "一",
    "Tue": "二",
    "Wed": "三",
    "Thu": "四",
    "Fri": "五",
    "Sat": "六",
}
PERIOD_START_MINUTES = {
    "1": 8 * 60,
    "2": 9 * 60,
    "3": 10 * 60,
    "4": 11 * 60,
    "5": 13 * 60,
    "6": 14 * 60,
    "7": 15 * 60,
    "8": 16 * 60,
    "9": 17 * 60,
    "A": 18 * 60,
    "B": 19 * 60,
    "C": 20 * 60,
}


def clean_text(text):
    """整理 HTML 文字中的空白。"""
    return " ".join(text.split())


class CourseRowsParser(HTMLParser):
    """從官方查詢結果的表格列擷取課程欄位。"""

    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.special_field = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "chinese_name": "", "time": ""}
        elif tag == "span" and self.cell is not None:
            class_name = attributes.get("class", "")
            if "engclass" in class_name:
                self.special_field = "chinese_name"
            elif "classtime" in class_name:
                self.special_field = "time"
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += " "
            if self.special_field:
                self.cell[self.special_field] += " "

    def handle_data(self, data):
        if self.cell is None:
            return
        self.cell["text"] += data
        if self.special_field:
            self.cell[self.special_field] += data

    def handle_endtag(self, tag):
        if tag == "span":
            self.special_field = None
        elif tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def get_term(page_html):
    """從官方查詢頁面找出目前預選的學期代碼。"""
    match = re.search(
        r"<option\s+selected\s+value=['\"](\d{4})['\"]",
        page_html,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("無法從官方查詢頁面辨認目前學期，請手動指定 --semester。")
    return match.group(1)


def get_departments(session, semester):
    """透過官方查詢頁面的公開服務取得指定學期開課單位。"""
    session_id = session.cookies.get("JSESSIONID", "")
    if not session_id:
        raise RuntimeError("官方查詢頁面沒有提供工作階段，無法載入開課單位。")

    body = "\n".join([
        "callCount=1",
        "page=" + QUERY_PATH,
        "httpSessionId=" + session_id,
        "scriptSessionId=courseHelperDemoSession",
        "windowName=courseHelperDemoWindow",
        "c0-scriptName=CourseSearchService",
        "c0-methodName=getUnitSelection",
        "c0-id=0",
        "c0-param0=string:" + semester,
        "batchId=0",
    ])
    response = session.post(
        BASE_URL + DEPARTMENT_PATH,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Referer": BASE_URL + QUERY_PATH,
        },
        timeout=20,
    )
    response.raise_for_status()

    match = re.search(r'handleCallback\("0","0",(\[.*\])\);', response.text, re.DOTALL)
    if not match:
        raise RuntimeError("官方查詢服務沒有回傳開課單位清單。")

    json_text = re.sub(
        r'(?<=[{,])([A-Za-z][A-Za-z0-9_]*):',
        r'"\1":',
        match.group(1),
    )
    try:
        departments = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("無法讀取官方開課單位清單：" + str(error)) from error
    return departments


def find_department(departments, department_name):
    """依中英文名稱找出單一開課單位。"""
    matches = []
    for department in departments:
        names = department.get("deptName", [])
        if any(department_name == name for name in names):
            return department
        if any(department_name in name for name in names):
            matches.append(department)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = [item["deptName"][0] for item in matches]
        raise ValueError("開課單位名稱不夠明確，請選擇其中一個：" + "、".join(names))

    available = []
    for department in departments:
        names = department.get("deptName", [])
        if names and not department.get("key", "").startswith("college_"):
            available.append(names[0])
    raise ValueError(
        "找不到開課單位「"
        + department_name
        + "」。可用單位例如："
        + "、".join(available[:20])
    )


def format_clock_time(minutes):
    """把分鐘數轉成 HH:MM 時間字串。"""
    return str(minutes // 60).zfill(2) + ":" + str(minutes % 60).zfill(2)


def meeting_times_for_periods(day_name, periods):
    """依已確認的中大節次對照時間；無法辨識的節次保留原碼。"""
    if not periods or any(period not in PERIOD_START_MINUTES for period in periods):
        return [{"day": day_name, "periods": periods}]

    period_groups = []
    current_group = periods[0]
    for period in periods[1:]:
        previous_start = PERIOD_START_MINUTES[current_group[-1]]
        current_start = PERIOD_START_MINUTES[period]
        if current_start - previous_start == 60:
            current_group += period
        else:
            period_groups.append(current_group)
            current_group = period
    period_groups.append(current_group)

    meetings = []
    for group in period_groups:
        start = PERIOD_START_MINUTES[group[0]]
        end = PERIOD_START_MINUTES[group[-1]] + 50
        meetings.append({
            "day": day_name,
            "periods": group,
            "start": format_clock_time(start),
            "end": format_clock_time(end),
        })
    return meetings


def parse_meeting_days(time_text):
    """從官方節次文字擷取星期，並轉換可辨識的節次鐘點。"""
    meetings = []
    for day_code, periods in re.findall(
        r"\b(Sun|Mon|Tue|Wed|Thu|Fri|Sat)([0-9A-Z]+)",
        time_text,
    ):
        meetings.extend(meeting_times_for_periods(DAY_NAMES[day_code], periods))
    return meetings


def parse_course_restrictions(remark_text):
    """整理官方課程備註中的密碼卡與初選分發狀態。"""
    card_match = re.search(
        r"\[\s*Code\s*Card\s*:\s*([^\]]+)\]",
        remark_text,
        re.IGNORECASE,
    )
    if not card_match:
        card_requirement = "未提供"
    else:
        card_value = clean_text(card_match.group(1)).lower()
        if card_value == "required":
            card_requirement = "需要"
        elif card_value == "optional":
            card_requirement = "可選"
        elif card_value in ["no", "none", "not required"]:
            card_requirement = "不需要"
        else:
            card_requirement = "未提供"

    not_for_preliminary = None
    if re.search(r"\[\s*Not\s+for\s+preliminary\s*\]", remark_text, re.IGNORECASE):
        not_for_preliminary = True
    return card_requirement, not_for_preliminary


def parse_courses(page_html, semester, department_name, source_url):
    """讀取官方查詢結果列並轉成 courses.json 的資料格式。"""
    parser = CourseRowsParser()
    parser.feed(page_html)
    courses = []
    course_id_pattern = re.compile(r"^\s*(\d{5})\s+([A-Z0-9]+-[A-Z0-9*]+)")

    for row in parser.rows:
        if len(row) < 5:
            continue
        first_cell = clean_text(row[0]["text"])
        match = course_id_pattern.search(first_cell)
        if not match:
            continue

        course_name = clean_text(row[1]["chinese_name"])
        if not course_name:
            course_name = re.sub(r"\[[^\]]*\]", "", clean_text(row[1]["text"]))
        if not course_name or "Course Cancelled" in row[1]["text"]:
            continue

        credits_text = clean_text(row[3]["text"])
        try:
            credits = int(credits_text)
        except ValueError:
            continue

        time_text = clean_text(row[4]["time"]) or clean_text(row[4]["text"])
        offering_type = clean_text(row[5]["text"]) if len(row) > 5 else ""
        offering_type_lower = offering_type.lower()
        if "required" in offering_type_lower or "必修" in offering_type:
            is_required = True
            offering_type = "必修"
        elif "elective" in offering_type_lower or "選修" in offering_type:
            is_required = False
            offering_type = "選修"
        else:
            is_required = None
            offering_type = "未提供"
        code_card_requirement, not_for_preliminary = parse_course_restrictions(
            row[1]["text"]
        )
        serial_number = match.group(1)
        course_id = match.group(2)
        courses.append({
            "offering_id": semester + "-" + serial_number,
            "course_id": course_id,
            "serial_number": serial_number,
            "course_name": course_name,
            "department": department_name,
            "target_year": "未提供",
            "section": course_id.rsplit("-", 1)[-1],
            "credits": credits,
            "is_required": is_required,
            "offering_type": offering_type,
            "code_card_requirement": code_card_requirement,
            "not_for_preliminary": not_for_preliminary,
            "teacher": clean_text(row[2]["text"]) or "未提供",
            "teacher_gmail": "未提供",
            "time": time_text or "未提供",
            "meeting_times": parse_meeting_days(time_text),
            "grading": "未提供",
            "teaching_style": "未提供",
            "reviews": [],
            "semester": semester,
            "sources": [{
                "name": "中央大學新課程規劃系統",
                "url": source_url,
                "fields": [
                    "course_id",
                    "course_name",
                    "teacher",
                    "time",
                    "meeting_times",
                    "credits",
                    "offering_type",
                    "code_card_requirement",
                    "not_for_preliminary",
                ],
                "checked_at": datetime.date.today().isoformat(),
                "note": "time 保留官方原文；meeting_times 依中大節次對照換算，未辨識節次保留原碼",
            }],
        })
    return courses


def scrape_courses(semester=None, department_name=DEFAULT_DEPARTMENT):
    """查詢一個學期、單一開課單位的公開課程資料。"""
    session = requests.Session()
    response = session.get(BASE_URL + QUERY_PATH, timeout=20)
    response.raise_for_status()
    if not semester:
        semester = get_term(response.text)
    if not re.fullmatch(r"\d{4}", semester):
        raise ValueError("學期格式需為四碼，例如 1151。")

    departments = get_departments(session, semester)
    department = find_department(departments, department_name)
    department_label = department["deptName"][0]

    parameters = {
        "year": semester[:3],
        "fall_spring": semester[-1],
        "selectDept": department["key"],
        "keyword": "",
        "week": "",
        "day": "",
        "crs_lang_no": "0",
        "query": "Search",
    }
    results = session.get(
        BASE_URL + QUERY_PATH,
        params=parameters,
        timeout=30,
    )
    results.raise_for_status()
    source_url = results.url
    courses = parse_courses(results.text, semester, department_label, source_url)
    if not courses:
        raise RuntimeError(
            "官方查詢頁沒有找到課程資料。請確認學期與開課單位，"
            "或檢查官方頁面是否已改版。"
        )
    return courses


def main():
    parser = argparse.ArgumentParser(
        description="查詢中大官方課程系統的指定學期與開課單位。"
    )
    parser.add_argument(
        "--semester",
        help="學期代碼，例如 1151；省略時抓取 9 個文理學院單位與 2 個通識單位",
    )
    parser.add_argument(
        "--department",
        action="append",
        help="開課單位名稱；可重複指定。搭配 --semester 使用",
    )
    parser.add_argument(
        "--output",
        default="courses.json",
        help="輸出 JSON 檔案名稱，預設 courses.json",
    )
    arguments = parser.parse_args()

    try:
        if arguments.semester is None and not arguments.department:
            queries = DEFAULT_DEMO_QUERIES
        else:
            semester = arguments.semester or DEFAULT_SEMESTER
            departments = arguments.department or FALLBACK_DEPARTMENTS.get(
                semester,
                [DEFAULT_DEPARTMENT],
            )
            queries = []
            for department in departments:
                queries.append((semester, department))

        courses = []
        for semester, department in queries:
            courses.extend(scrape_courses(semester, department))
        with open(arguments.output, "w", encoding="utf-8") as output_file:
            json.dump(courses, output_file, ensure_ascii=False, indent=2)
    except (OSError, requests.RequestException, RuntimeError, ValueError) as error:
        print("擷取失敗：" + str(error), file=sys.stderr)
        return 1

    semesters = sorted(set(course["semester"] for course in courses))
    departments = sorted(set(course["department"] for course in courses))
    print("已儲存 " + str(len(courses)) + " 門課程至 " + arguments.output + "。")
    print("學期：" + "、".join(semesters))
    print("開課單位：" + "、".join(departments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
