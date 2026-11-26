import hashlib
import html
import json
import re
from datetime import date, timedelta

import streamlit as st
from calendar_export import (
    DAY_NAMES,
    default_course_color,
    default_week_one_monday,
    dates_for_week,
    event_color,
    render_calendar_png,
    valid_calendar_color,
)
from course_workspace import (
    load_course_workspace,
    load_user_profile,
    save_course_workspace,
)


GENERAL_EDUCATION_DEPARTMENTS = ["核心通識課程", "通識教育中心"]
UNDERGRADUATE_YEAR_OPTIONS = ["大一", "大二", "大三", "大四"]


def load_menu(file_path):
    """讀取課程資料；讀檔或格式錯誤時回傳空清單和錯誤訊息。"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            courses = json.load(file)
        if not isinstance(courses, list):
                return [], file_path + " 最外層格式錯誤：應為 JSON 陣列"
        return courses, ""
    except FileNotFoundError:
        return [], "找不到 " + file_path + "，請先準備課程資料檔。"
    except json.JSONDecodeError as error:
        return [], file_path + " 的 JSON 格式錯誤：" + str(error)
    except OSError as error:
        return [], "讀取 " + file_path + " 失敗：" + str(error)


def load_curriculum(file_path):
    """讀取小組人工核對的系級課程與通識分類資料。"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return {}, file_path + " 格式錯誤：最外層應為 JSON 物件"
        if not isinstance(data.get("department_curricula", []), list):
            return {}, file_path + " 的 department_curricula 應為 JSON 陣列"
        if not isinstance(data.get("general_education_categories", []), list):
            return {}, file_path + " 的 general_education_categories 應為 JSON 陣列"
        for index, record in enumerate(data.get("department_curricula", [])):
            if not isinstance(record, dict):
                return {}, file_path + " 的第 " + str(index + 1) + " 筆系級課程資料應為 JSON 物件"
            for field in ["required_course_ids", "elective_course_ids"]:
                values = record.get(field, [])
                if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                    return {}, file_path + " 的系級課程欄位 " + field + " 應為字串陣列"
            sources = record.get("sources", [])
            if not valid_sources(sources):
                return {}, file_path + " 的每筆系級課程資料都要提供含名稱和網址的 sources"
        for index, category in enumerate(data.get("general_education_categories", [])):
            if not isinstance(category, dict):
                return {}, file_path + " 的第 " + str(index + 1) + " 筆通識分類應為 JSON 物件"
            course_ids = category.get("course_ids", [])
            if not isinstance(course_ids, list) or not all(isinstance(value, str) for value in course_ids):
                return {}, file_path + " 的通識分類 course_ids 應為字串陣列"
            if not isinstance(category.get("name"), str) or not category.get("name", "").strip():
                return {}, file_path + " 的每個通識分類都要有 name"
            if not valid_sources(category.get("sources", [])):
                return {}, file_path + " 的每個通識分類都要提供含名稱和網址的 sources"
        return data, ""
    except FileNotFoundError:
        return {}, "找不到 " + file_path + "。請建立檔案並填入已核對的課程地圖。"
    except json.JSONDecodeError as error:
        return {}, file_path + " 的 JSON 格式錯誤：" + str(error)
    except OSError as error:
        return {}, "讀取 " + file_path + " 失敗：" + str(error)


def valid_sources(sources):
    """確認人工核對資料附有可追溯的來源名稱與網址。"""
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict):
            return False
        if not source.get("name") or not source.get("url"):
            return False
    return True


def search_courses(courses, keyword):
    """依課名、教師或系所關鍵字搜尋課程。"""
    if not keyword or not keyword.strip():
        return courses

    keyword = keyword.strip().lower()
    result = []
    for course in courses:
        course_name = str(course.get("course_name", "")).lower()
        course_id = str(course.get("course_id", "")).lower()
        teacher = str(course.get("teacher", "")).lower()
        department = str(course.get("department", "")).lower()
        if (
            keyword in course_name
            or keyword in course_id
            or keyword in teacher
            or keyword in department
        ):
            result.append(course)
    return result


def courses_for_semester(courses, semester):
    """只回傳指定學期的課程，避免不同學期混在一起比較。"""
    result = []
    for course in courses:
        if str(course.get("semester", "未提供")) == semester:
            result.append(course)
    return result


def departments_for_selection(courses):
    """取得系所選單；核心通識保留為課程資料，但不列為系所。"""
    departments = []
    for course in courses:
        department = course.get("department", "")
        if (
            department
            and department != "未提供"
            and department not in GENERAL_EDUCATION_DEPARTMENTS
            and department not in departments
        ):
            departments.append(department)
    return departments


def course_type_label(course):
    """分辨系所課程、核心通識和一般通識。"""
    department = course.get("department")
    if department == "核心通識課程":
        return "核心通識"
    if department == "通識教育中心":
        return "一般通識"
    return "系所課程"


def general_education_category_label(course, category_map):
    """只對通識課程顯示分類；系所課程使用破折號。"""
    if course_type_label(course) == "系所課程":
        return "—"
    return category_map.get(course.get("course_id"), "未分類")


def filter_course_scope(courses, course_scope, selected_category, category_map):
    """依系所／通識範圍和已核對的通識類型篩選課程。"""
    result = []
    for course in courses:
        course_type = course_type_label(course)
        if course_scope == "系所課程" and course_type != "系所課程":
            continue
        if course_scope == "通識課程" and course_type == "系所課程":
            continue
        if selected_category and category_map.get(course.get("course_id")) != selected_category:
            continue
        result.append(course)
    return result


def filter_schedule_courses(courses, department="", target_year="", section=""):
    """依系所年級和可選班別篩選可直接加入課表的課程。"""
    result = []
    for course in courses:
        if department and course.get("department") != department:
            continue
        course_year = course.get("target_year")
        if (
            target_year
            and course_year not in [target_year, "不限"]
            and course_year not in [None, "", "未提供"]
        ):
            continue
        if section and course.get("section") not in [section, "*", "不限"]:
            continue
        result.append(course)
    return result


def find_curriculum(curriculum_data, department, grade, semester):
    """依系所、年級和學期找出人工核對的課程規定。"""
    for record in curriculum_data.get("department_curricula", []):
        if (
            record.get("department") == department
            and str(record.get("grade")) == str(grade)
            and record.get("semester") == semester
        ):
            return record
    return None


def get_course_categories(curriculum_data):
    """建立課號到官方通識類別的對照表。"""
    categories = {}
    for category in curriculum_data.get("general_education_categories", []):
        category_name = category.get("name", "")
        for course_id in category.get("course_ids", []):
            categories[course_id] = category_name
    return categories


def course_interest_score(course, interests):
    """以課名、課號和系所的關鍵字符合數計算興趣分數。"""
    course_text = (
        str(course.get("course_name", ""))
        + " "
        + str(course.get("course_id", ""))
        + " "
        + str(course.get("department", ""))
    ).lower()
    score = 0
    for interest in interests:
        if interest.lower() in course_text:
            score += 1
    return score


def course_preferred_day_score(course, preferred_days):
    """計算課程有幾個上課日符合使用者偏好。"""
    score = 0
    for meeting in course.get("meeting_times", []):
        if meeting.get("day") in preferred_days:
            score += 1
    return score


def course_preferred_time_score(course, preferred_time_slots):
    """計算課程時間和已選偏好時段的重疊數。"""
    score = 0
    for selected_slot in preferred_time_slots:
        day_name, start_minutes = selected_slot.split("|", 1)
        slot_start = int(start_minutes)
        slot_end = slot_start + 60
        for meeting in course.get("meeting_times", []):
            if (
                meeting.get("day") == day_name
                and meeting.get("start")
                and meeting.get("end")
                and time_in_minutes(meeting["start"]) < slot_end
                and time_in_minutes(meeting["end"]) > slot_start
            ):
                score += 1
                break
    return score


def courses_for_recommendation(courses, department, curriculum_record):
    """沒有系級課程地圖時，只推薦使用者選定系所的課程。"""
    if curriculum_record or not department:
        return courses
    result = []
    for course in courses:
        if course.get("department") == department or course.get("department") in GENERAL_EDUCATION_DEPARTMENTS:
            result.append(course)
    return result


def recommend_schedules(
    courses,
    curriculum_record,
    interests,
    target_credits,
    maximum_credits,
    option_count,
    selected_categories,
    category_map,
    preferred_days=None,
    preferred_time_slots=None,
):
    """依系級、興趣、偏好上課日和學分條件建立多套課表草案。"""
    preferred_days = preferred_days or []
    preferred_time_slots = preferred_time_slots or []
    required_ids = []
    elective_ids = []
    if curriculum_record:
        required_ids = curriculum_record.get("required_course_ids", [])
        elective_ids = curriculum_record.get("elective_course_ids", [])

    required_courses = []
    missing_required = []
    for course_id in required_ids:
        found = False
        for course in courses:
            if course.get("course_id") == course_id:
                required_courses.append(course)
                found = True
                break
        if not found:
            missing_required.append(course_id)

    required_offering_ids = []
    for course in required_courses:
        required_offering_ids.append(course.get("offering_id"))

    candidates = []
    for course in courses:
        if course.get("offering_id") in required_offering_ids:
            continue
        if selected_categories and category_map.get(course.get("course_id")) not in selected_categories:
            continue
        candidates.append(course)

    candidates.sort(
        key=lambda course: (
            -course_preferred_time_score(course, preferred_time_slots),
            -course_preferred_day_score(course, preferred_days),
            -course_interest_score(course, interests),
            0 if course.get("course_id") in elective_ids else 1,
            str(course.get("course_name", "")),
        )
    )

    credits_limit = maximum_credits or target_credits or 12
    target = target_credits or credits_limit
    schedules = []
    seen_schedules = []
    for option_index in range(option_count):
        option_courses = list(required_courses)
        total_credits = 0
        used_course_ids = []
        for course in required_courses:
            credits = course.get("credits", 0)
            if isinstance(credits, (int, float)):
                total_credits += credits
            used_course_ids.append(course.get("course_id"))

        if candidates:
            offset = option_index % len(candidates)
            rotated_candidates = candidates[offset:] + candidates[:offset]
        else:
            rotated_candidates = []

        for course in rotated_candidates:
            course_id = course.get("course_id")
            credits = course.get("credits", 0)
            if course_id in used_course_ids:
                continue
            if not isinstance(credits, (int, float)) or credits <= 0:
                continue
            if total_credits + credits > target or total_credits + credits > credits_limit:
                continue
            option_courses.append(course)
            used_course_ids.append(course_id)
            total_credits += credits

        signature = tuple(sorted(used_course_ids))
        if signature in seen_schedules:
            continue
        seen_schedules.append(signature)
        schedules.append({
            "courses": option_courses,
            "credits": total_credits,
        })

    return schedules, missing_required


def filter_courses(courses, required, credits, days, teacher):
    """依使用者明確選取的必修、學分、上課日或教師條件篩選。"""
    result = []
    for course in courses:
        if required and "不限" not in required:
            if "必修" in required and course.get("is_required") is not True:
                continue
            if "選修" in required and course.get("is_required") is not False:
                continue

        if credits:
            if course.get("credits") not in credits:
                continue

        if days:
            course_days = []
            for meeting in course.get("meeting_times", []):
                course_days.append(meeting.get("day", ""))
            matched_day = False
            for day in days:
                if day in course_days:
                    matched_day = True
            if not matched_day:
                continue

        if teacher:
            if course.get("teacher", "") not in teacher:
                continue

        result.append(course)
    return result


def compare_courses(courses, offering_ids, category_map=None):
    """依唯一 offering_id 選回課程，並保留每筆資料的來源。"""
    category_map = category_map or {}
    result = []
    for offering_id in offering_ids:
        for course in courses:
            if course.get("offering_id") == offering_id:
                selected = {
                    "offering_id": course.get("offering_id", "未提供"),
                    "course_name": course.get("course_name", "未提供"),
                    "course_id": course.get("course_id", "未提供"),
                    "department": course.get("department", "未提供"),
                    "section": course.get("section", "未提供"),
                    "teacher": course.get("teacher", "未提供"),
                    "teacher_gmail": verified_teacher_gmail(course),
                    "code_card_requirement": course.get("code_card_requirement", "未提供"),
                    "not_for_preliminary": course.get("not_for_preliminary"),
                    "course_type": course_type_label(course),
                    "general_education_category": general_education_category_label(
                        course,
                        category_map,
                    ),
                    "is_required": course.get("is_required"),
                    "credits": course.get("credits", "未提供"),
                    "meeting_times": course.get("meeting_times", []),
                    "time": format_course_time(course),
                    "official_time": course.get("time", ""),
                    "grading": course.get("grading", "未提供"),
                    "teaching_style": course.get("teaching_style", "未提供"),
                    "reviews": course.get("reviews", []),
                    "sources": course.get("sources", []),
                }
                result.append(selected)
    return result


def summarize_comparison(selected_courses):
    """只把已選課程欄位及來源送至既有 OpenAI API，產生簡短摘要。"""
    api_key = None
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        return "", "AI 摘要不可用：尚未設定 Streamlit secrets 中的 OPENAI_API_KEY。"

    if not api_key:
        return "", "AI 摘要不可用：OPENAI_API_KEY 是空的。"

    payload = []
    for course in selected_courses:
        payload.append({
            "course_name": course.get("course_name", "未提供"),
            "course_id": course.get("course_id", "未提供"),
            "teacher": course.get("teacher", "未提供"),
            "code_card_requirement": course.get("code_card_requirement", "未提供"),
            "not_for_preliminary": course.get("not_for_preliminary"),
            "is_required": course.get("is_required"),
            "credits": course.get("credits", "未提供"),
            "meeting_times": course.get("meeting_times", []),
            "time": course.get("time", ""),
            "official_time": course.get("official_time", ""),
            "grading": course.get("grading", "未提供"),
            "teaching_style": course.get("teaching_style", "未提供"),
            "reviews": course.get("reviews", []),
            "sources": course.get("sources", []),
        })

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "請只根據下列 JSON 資料整理 3 至 6 點短小的課程差異。"
            "不要新增資料，不要推測教師風格或課程評價。"
            "資料不足時要明確寫「資料不足，無法比較」。"
            "請用繁體中文回答，並在適當處標示資料來源名稱。\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是只根據提供資料整理課程差異的助理。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        summary = response.choices[0].message.content
        if not summary:
            return "", "AI 摘要未產生：API 沒有回傳摘要文字。"
        return summary, ""
    except Exception as error:
        return "", "AI 摘要未產生：API 呼叫失敗：" + str(error)


def chat_schedule(profile, question, courses, chat_history):
    """依學生條件和 JSON 課程資料，與學生對話並擬定課表草案。"""
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        return "", "AI 課表規劃不可用：尚未設定 Streamlit secrets 中的 OPENAI_API_KEY。"

    if not api_key:
        return "", "AI 課表規劃不可用：OPENAI_API_KEY 是空的。"

    safe_courses = []
    for course in courses:
        safe_courses.append({
            "offering_id": course.get("offering_id", "未提供"),
            "course_id": course.get("course_id", "未提供"),
            "course_name": course.get("course_name", "未提供"),
            "department": course.get("department", "未提供"),
            "target_year": course.get("target_year", "未提供"),
            "section": course.get("section", "未提供"),
            "credits": course.get("credits", "未提供"),
            "is_required": course.get("is_required"),
            "teacher": course.get("teacher", "未提供"),
            "code_card_requirement": course.get("code_card_requirement", "未提供"),
            "not_for_preliminary": course.get("not_for_preliminary"),
            "meeting_times": course.get("meeting_times", []),
            "time": format_course_time(course),
            "official_time": course.get("time", ""),
            "grading": course.get("grading", "未提供"),
            "teaching_style": course.get("teaching_style", "未提供"),
            "reviews": course.get("reviews", []),
            "sources": course.get("sources", []),
        })

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "你是中央大學選課規劃助理。請只依下列學生條件與課程 JSON 回答。"
            "不要新增不存在的課程、教師、班別、學分、時間、評分或來源。"
            "若課程資料標示需要密碼卡或不列入初選分發，請清楚提醒使用者。"
            "meeting_times 的 start/end 是依已確認的中大節次表換算；official_time 保留官方原文。"
            "若 meeting_times 缺少 start/end，不可自行推測鐘點。"
            "若教師或時間標示未提供，請清楚指出，不要替課程安排虛構的時間或教師。"
            "請先確認學生目標，再提出課表草案。課表草案只能挑選 JSON 中的 offering_id。"
            "請詢問資料不足的重要問題，例如系所、年級、畢業/系級必修、已修課、想修學分、"
            "不可上課時間、偏好的上課日或鐘點時段、老師、課業負荷、實習或社團活動。"
            "資料不足時不要假裝知道，明確說明需要補充。"
            "不要宣稱已檢查衝堂或時段衝突；明確提醒使用者到選課系統確認。"
            "回答請用繁體中文，包含：可考量因素、草案課表、未確認事項、建議下一步。"
            "不要傳送或保存姓名、學號或其他可識別個人資訊。\n\n"
            "學生條件：" + json.dumps(profile, ensure_ascii=False) + "\n\n"
            "課程 JSON：" + json.dumps(safe_courses, ensure_ascii=False) + "\n\n"
            "學生問題：" + question
        )

        messages = [
            {"role": "system", "content": "你只能根據提供的課程資料回答，不可編造。"},
        ]
        for chat in chat_history[-8:]:
            messages.append({
                "role": chat["role"],
                "content": chat["content"],
            })
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content
        if not answer:
            return "", "AI 課表規劃未產生：API 沒有回傳內容。"
        return answer, ""
    except Exception as error:
        return "", "AI 課表規劃未產生：API 呼叫失敗：" + str(error)


def format_required(value):
    """把必選修布林值轉成介面文字。"""
    if value is True:
        return "必修"
    if value is False:
        return "選修"
    return "未提供"


def format_course_restrictions(course):
    """清楚呈現課程的密碼卡和初選分發限制。"""
    card_requirement = course.get("code_card_requirement", "未提供")
    if card_requirement == "需要":
        card_label = "需要密碼卡"
    elif card_requirement == "可選":
        card_label = "密碼卡可選"
    elif card_requirement == "不需要":
        card_label = "不需要密碼卡"
    else:
        card_label = "密碼卡狀態未提供"

    preliminary_status = course.get("not_for_preliminary")
    if preliminary_status is True:
        distribution_label = "不列入初選分發"
    elif preliminary_status is False:
        distribution_label = "官方未標示初選限制"
    else:
        distribution_label = "初選分發狀態未提供"
    return card_label + "；" + distribution_label


def valid_teacher_gmail(value):
    """只回傳格式有效的 Gmail 地址，不推測教師信箱。"""
    if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9._%+-]+@gmail\.com",
        value,
        re.IGNORECASE,
    ):
        return value
    return ""


def verified_teacher_gmail(course):
    """只顯示有來源明確支持的教師 Gmail。"""
    email = valid_teacher_gmail(course.get("teacher_gmail", ""))
    if not email:
        return ""
    for source in course.get("sources", []):
        if (
            "teacher_gmail" in source.get("fields", [])
            and source.get("url")
        ):
            return email
    return ""


def show_teacher_gmail(value):
    """顯示已核對的教師 Gmail；沒有資料時明確標示。"""
    email = valid_teacher_gmail(value)
    if email:
        st.markdown("[寄信給老師：" + email + "](mailto:" + email + ")")
    else:
        st.write("老師 Gmail：未提供")


def format_times(meeting_times):
    """把上課時段轉成鐘點；尚未換算的資料保留節次代碼。"""
    if not meeting_times:
        return "未提供"
    times = []
    for meeting in meeting_times:
        day = meeting.get("day", "未提供")
        start = meeting.get("start")
        end = meeting.get("end")
        if start and end:
            times.append(day + " " + str(start) + "-" + str(end))
        elif meeting.get("periods"):
            times.append(day + " 第" + str(meeting["periods"]) + "節（未換算）")
        else:
            times.append(day + " 時間未提供")
    return "、".join(times)


def format_course_time(course):
    """優先顯示換算後的上課鐘點，沒有結構化時段時保留官方原文。"""
    meeting_times = course.get("meeting_times", [])
    if meeting_times:
        return format_times(meeting_times)
    return str(course.get("time") or "未提供")


def show_sources(sources):
    """顯示來源、連結、支持欄位與查核日期。"""
    if not sources:
        st.write("未提供")
        return
    for source in sources:
        st.markdown("- **來源：** " + str(source.get("name", "未提供")))
        url = source.get("url", "")
        if url:
            st.markdown("  - [開啟來源](" + str(url) + ")")
        fields = source.get("fields", [])
        st.write("  - 支持欄位：" + ("、".join(fields) if fields else "未提供"))
        st.write("  - 查核日期：" + str(source.get("checked_at", "未提供")))
        if source.get("note"):
            st.write("  - 備註：" + str(source["note"]))


def make_schedule_event(course):
    """把一個課程班別轉成週曆上的課堂事件。"""
    events = []
    for meeting in course.get("meeting_times", []):
        if not meeting.get("start") or not meeting.get("end"):
            continue
        events.append({
            "id": course["offering_id"] + "-" + meeting.get("day", "") + "-" + meeting.get("start", ""),
            "title": course.get("course_name", "未提供"),
            "offering_id": course.get("offering_id", "未提供"),
            "semester": course.get("semester", "未提供"),
            "day": meeting.get("day", ""),
            "start": meeting.get("start", "未提供"),
            "end": meeting.get("end", "未提供"),
            "teacher": course.get("teacher", "未提供"),
            "color": (
                course.get("color")
                if valid_calendar_color(course.get("color"))
                else default_course_color(course.get("offering_id"))
            ),
            "todo": "",
            "grades": [],
        })
    return events


def valid_time(time_text):
    """檢查時間是否為 HH:MM 格式。"""
    if len(time_text) != 5:
        return False
    if time_text[2] != ":":
        return False
    hour = time_text[0:2]
    minute = time_text[3:5]
    if not hour.isdigit() or not minute.isdigit():
        return False
    if int(hour) > 23 or int(minute) > 59:
        return False
    return True


def add_event_to_schedule(event):
    """新增或更新一堂週曆課程。"""
    if "schedule_events" not in st.session_state:
        load_schedule()
    for index, old_event in enumerate(st.session_state.schedule_events):
        if old_event["id"] == event["id"]:
            st.session_state.schedule_events[index] = event
            save_schedule()
            return
    st.session_state.schedule_events.append(event)
    save_schedule()


def save_schedule():
    """把週課表、待辦與成績保存到本機 JSON 檔案。"""
    try:
        with open("schedule.json", "w", encoding="utf-8") as file:
            json.dump(st.session_state.schedule_events, file, ensure_ascii=False)
        return True
    except OSError as error:
        st.warning("週課表暫時無法保存到本機：" + str(error))
        return False


def load_schedule():
    """讀取本機週課表；檔案不存在時使用空課表。"""
    try:
        with open("schedule.json", "r", encoding="utf-8") as file:
            events = json.load(file)
        if isinstance(events, list):
            st.session_state.schedule_events = events
    except FileNotFoundError:
        st.session_state.schedule_events = []
    except json.JSONDecodeError:
        st.session_state.schedule_events = []
        st.warning("schedule.json 格式錯誤，本次使用空課表。")
    except OSError as error:
        st.session_state.schedule_events = []
        st.warning("讀取週課表失敗：" + str(error))


def apply_schedule_plan(courses, semester):
    """把完整且有鐘點資料的推薦方案取代為本學期課表。"""
    if not courses:
        return False, ["方案沒有課程"], []

    seen_course_ids = []
    duplicate_course_ids = []
    missing_times = []
    new_events = []
    for course in courses:
        course_id = course.get("course_id", "未提供")
        if course_id in seen_course_ids:
            duplicate_course_ids.append(course_id)
        seen_course_ids.append(course_id)

        course_events = make_schedule_event(course)
        if not course_events:
            missing_times.append(str(course.get("course_name", course_id)))
            continue
        for event in course_events:
            if not valid_time(event.get("start", "")) or not valid_time(event.get("end", "")):
                missing_times.append(str(course.get("course_name", course_id)))
                break
            event["semester"] = semester
            new_events.append(event)

    if missing_times or duplicate_course_ids:
        return False, missing_times, duplicate_course_ids

    old_events = st.session_state.schedule_events
    kept_events = []
    for event in old_events:
        if event.get("semester", "1152") != semester or event.get("offering_id") == "CUSTOM":
            kept_events.append(event)
    st.session_state.schedule_events = kept_events + new_events
    if not save_schedule():
        st.session_state.schedule_events = old_events
        return False, [], []
    return True, [], []


def get_event_grade(event):
    """依成績項目的權重計算期末加權成績。"""
    total_weight = 0
    weighted_score = 0
    for grade in event.get("grades", []):
        score = grade.get("score")
        weight = grade.get("weight")
        if isinstance(score, (int, float)) and isinstance(weight, (int, float)):
            weighted_score = weighted_score + score * weight / 100
            total_weight = total_weight + weight
    if total_weight == 0:
        return None, 0
    return weighted_score, total_weight


def time_in_minutes(time_text):
    """把 HH:MM 轉成分鐘數，供課表格子判斷。"""
    hour = int(time_text[0:2])
    minute = int(time_text[3:5])
    return hour * 60 + minute


def format_table_time(minutes):
    """把分鐘數轉成 HH:MM 顯示格式。"""
    hour = minutes // 60
    minute = minutes % 60
    return str(hour).zfill(2) + ":" + str(minute).zfill(2)


def format_preferred_time_slots(preferred_time_slots):
    """把格子選取值轉成課表偏好時段文字。"""
    labels = []
    for selected_slot in preferred_time_slots:
        day_name, start_minutes = selected_slot.split("|", 1)
        start = int(start_minutes)
        labels.append(
            "星期"
            + day_name
            + " "
            + format_table_time(start)
            + "-"
            + format_table_time(start + 60)
        )
    return labels


def hourly_time_slots():
    """提供週課表每小時一格的時間列。"""
    return list(range(8 * 60, 23 * 60, 60))


def toggle_preferred_time_slot(day_name, start_minutes):
    """切換週課表上的一個偏好時段。"""
    selected_slot = day_name + "|" + str(start_minutes)
    preferred_time_slots = st.session_state.get("preferred_time_slots", [])
    if selected_slot in preferred_time_slots:
        preferred_time_slots.remove(selected_slot)
    else:
        preferred_time_slots.append(selected_slot)
    st.session_state["preferred_time_slots"] = preferred_time_slots


def show_week_calendar(courses, semester, curriculum_data=None):
    """顯示可編輯的一週課表和待辦事項。"""
    st.markdown("## 我的週課表")
    st.caption(
        "每列代表一小時；中大每節課為 50 分鐘，接著下課 10 分鐘。"
        "先產生課表，再編輯時間、標題、待辦事項或成績。草案不取代選課系統。"
    )
    st.caption(
        "點選下方星期欄可偏好整天；點選格子可偏好特定時段，"
        "符合偏好的課程會優先排列。"
    )
    if st.session_state.get("schedule_plan_notice"):
        st.success(st.session_state.schedule_plan_notice)
        del st.session_state.schedule_plan_notice

    if "schedule_events" not in st.session_state:
        load_schedule()

    departments = departments_for_selection(courses)
    year_options = list(UNDERGRADUATE_YEAR_OPTIONS)
    has_year_data = False
    for course in courses:
        course_year = str(course.get("target_year", ""))
        if course_year and course_year not in ["未提供", "不限"]:
            has_year_data = True
            if course_year not in year_options:
                year_options.append(course_year)
    section_options = sorted(set(
        str(course.get("section", ""))
        for course in courses
        if course.get("section")
        and course.get("section") not in ["未提供", "*", "不限"]
    ))

    generate_columns = st.columns([3, 1])
    with generate_columns[0]:
        selector_columns = st.columns(3)
        with selector_columns[0]:
            selected_department = st.selectbox(
                "系級－系所",
                [""] + departments,
                format_func=lambda value: value or "全部系所（含核心通識）",
                key="schedule_filter_department",
            )
        with selector_columns[1]:
            selected_target_year = st.selectbox(
                "系級－年級（可留空）",
                [""] + year_options,
                format_func=lambda value: value or "不指定年級",
                key="schedule_filter_target_year",
            )
        with selector_columns[2]:
            selected_section = st.selectbox(
                "班別（可留空）",
                [""] + section_options,
                format_func=lambda value: value or "不指定班別（包含未分班課程）",
                key="schedule_filter_section",
            )

        schedule_courses = filter_schedule_courses(
            courses,
            selected_department,
            selected_target_year,
            selected_section,
        )
        course_options = {}
        for course in schedule_courses:
            course_options[course["offering_id"]] = (
                str(course.get("course_name", "未提供"))
                + "｜"
                + str(course.get("teacher", "未提供"))
                + "｜"
                + str(course.get("section", "未提供"))
                + "｜"
                + format_course_restrictions(course)
                + "｜Gmail："
                + (verified_teacher_gmail(course) or "未提供")
            )

        generated_ids = st.multiselect(
            "手動選課班別（可留空，自動推薦）",
            list(course_options.keys()),
            format_func=lambda offering_id: course_options[offering_id],
            key="schedule_generate_courses",
        )
        if not has_year_data:
            st.caption(
                "目前課程資料沒有提供適用年級；選擇年級不會排除這些課程，"
                "請以官方資料確認。"
            )
        if not section_options:
            st.caption("目前課程資料沒有分班資訊；班別留空即可包含所有課程。")

    with generate_columns[1]:
        st.write("")
        if st.button(
            "直接產生課表",
            help="有選課時加入所選課程；未選課時，依條件自動推薦課表。",
        ):
            is_auto_recommendation = not generated_ids
            courses_to_add = []
            if generated_ids:
                courses_to_add = [
                    course
                    for course in schedule_courses
                    if course.get("offering_id") in generated_ids
                ]
            else:
                profile_department = st.session_state.get("planner_department", "")
                recommendation_department = selected_department or profile_department
                profile_grade = st.session_state.get("planner_grade", "")
                curriculum_record = find_curriculum(
                    curriculum_data or {},
                    recommendation_department,
                    profile_grade,
                    semester,
                )
                recommendation_courses = courses_for_recommendation(
                    schedule_courses,
                    recommendation_department,
                    curriculum_record,
                )
                interests = []
                interests_text = st.session_state.get("planner_interests", "")
                for interest in interests_text.replace("，", ",").replace("、", ",").split(","):
                    if interest.strip():
                        interests.append(interest.strip())
                category_map = get_course_categories(curriculum_data or {})
                selected_categories = st.session_state.get("planner_categories", [])
                preferred_days = st.session_state.get("preferred_days", [])
                preferred_time_slots = st.session_state.get("preferred_time_slots", [])
                recommendations, missing_required = recommend_schedules(
                    recommendation_courses,
                    curriculum_record,
                    interests,
                    st.session_state.get("planner_target_credits", 0),
                    st.session_state.get("planner_maximum_credits", 0),
                    1,
                    selected_categories,
                    category_map,
                    preferred_days,
                    preferred_time_slots,
                )
                if missing_required:
                    st.warning(
                        "課程地圖中的必修課未出現在目前資料："
                        + "、".join(missing_required)
                    )
                if not recommendations or not recommendations[0]["courses"]:
                    st.info("目前條件下沒有可推薦的課程，請調整系所、班別或學分條件。")
                else:
                    courses_to_add = recommendations[0]["courses"]
                    st.info("未手動選課，已依條件產生推薦課表草案。")
                    recommendation_rows = []
                    for course in courses_to_add:
                        recommendation_rows.append({
                            "課號": course.get("course_id", "未提供"),
                            "課名": course.get("course_name", "未提供"),
                            "教師": course.get("teacher", "未提供"),
                            "學分": course.get("credits", "未提供"),
                            "時間": format_course_time(course),
                        })
                    st.dataframe(
                        recommendation_rows,
                        width="stretch",
                        hide_index=True,
                    )

            if courses_to_add:
                applied, missing_times, duplicate_course_ids = apply_schedule_plan(
                    courses_to_add,
                    semester,
                )
                if applied:
                    notice = "推薦課表已加入週課表。"
                    if not is_auto_recommendation:
                        notice = "已將所選課程加入週課表。"
                    st.session_state.schedule_plan_notice = notice
                    st.rerun()
                if missing_times:
                    message = "所選課程"
                    if is_auto_recommendation:
                        message = "推薦課表"
                    st.warning(
                        message
                        + "的課程時間尚未提供可確認的鐘點，已列出但未放入週曆："
                        + "、".join(missing_times)
                        + "。請依官方時間確認後再排入。"
                    )
                elif duplicate_course_ids:
                    st.error(
                        ("推薦課表" if is_auto_recommendation else "所選課程")
                        + "含重複課號，未更動原課表："
                        + "、".join(duplicate_course_ids)
                    )
                elif not applied:
                    st.error("課表無法保存；原課表已保留。")

        if st.button("清空課表"):
            st.session_state.schedule_events = [
                event for event in st.session_state.schedule_events
                if event.get("semester", "1152") != semester
            ]
            save_schedule()
            st.rerun()

    day_names = DAY_NAMES
    visible_events = []
    for event in st.session_state.schedule_events:
        if event.get("semester", "1152") == semester:
            visible_events.append(event)

    workspace, workspace_error = load_course_workspace("course_workspace.json")
    if workspace_error:
        st.error(workspace_error)
        return
    saved_week_one = workspace["week_one_mondays"].get(semester)
    date_widget_key = "calendar_week_one_" + semester
    if date_widget_key not in st.session_state:
        if saved_week_one:
            st.session_state[date_widget_key] = date.fromisoformat(saved_week_one)
        else:
            st.session_state[date_widget_key] = default_week_one_monday(semester)

    st.markdown("### 學期行事曆")
    st.caption(
        "日期預設採該學期月份的第一個星期一，請依中央大學官方校曆調整後儲存。"
    )
    calendar_settings = st.columns([2, 1, 1])
    with calendar_settings[0]:
        week_one_monday = st.date_input(
            "第 1 週星期一日期",
            key=date_widget_key,
        )
    with calendar_settings[1]:
        week_number = st.selectbox(
            "查看第幾週",
            list(range(1, 21)),
            key="calendar_week_number_" + semester,
        )
    with calendar_settings[2]:
        st.write("")
        if st.button("儲存學期日期", key="save_calendar_dates_" + semester):
            if week_one_monday.weekday() != 0:
                st.error("第 1 週日期必須選星期一。")
            else:
                workspace["week_one_mondays"][semester] = week_one_monday.isoformat()
                save_error = save_course_workspace(
                    workspace,
                    "course_workspace.json",
                )
                if save_error:
                    st.error(save_error)
                else:
                    st.success("學期日期已儲存在本機。")

    calendar_valid = week_one_monday.weekday() == 0
    week_dates = []
    if calendar_valid:
        week_dates = dates_for_week(week_one_monday, week_number)
        st.markdown(
            "#### 第 "
            + str(week_number)
            + " 週｜"
            + week_dates[0].strftime("%Y/%m/%d")
            + "–"
            + week_dates[-1].strftime("%Y/%m/%d")
        )
    else:
        st.warning("請將第 1 週日期設為星期一，才能顯示正確週次與日期。")

    preferred_time_slots = set(st.session_state.get("preferred_time_slots", []))
    preference_columns = st.columns(7)
    manually_preferred_days = []
    for day_name, column in zip(day_names, preference_columns):
        with column:
            if st.toggle(
                "星期" + day_name,
                key="preferred_day_" + day_name,
            ):
                manually_preferred_days.append(day_name)

    preferred_days_from_slots = []
    for day_name in day_names:
        if any(slot.startswith(day_name + "|") for slot in preferred_time_slots):
            preferred_days_from_slots.append(day_name)
    preferred_days = [
        day_name
        for day_name in day_names
        if day_name in manually_preferred_days or day_name in preferred_days_from_slots
    ]
    st.session_state["preferred_days"] = preferred_days

    st.markdown("### 偏好時段（點選格子）")
    st.caption("每格代表一小時；已選格子會以顏色標記，再點一次即可取消。")
    header_cells = st.columns([0.8] + [1] * 7, gap="small")
    header_cells[0].markdown("**時間**")
    for index, day_name in enumerate(day_names):
        day_label = "星期" + day_name
        if day_name in preferred_days:
            day_label += "（偏好）"
        date_label = ""
        if calendar_valid:
            date_label = "<br>" + week_dates[index].strftime("%Y/%m/%d")
        header_cells[index + 1].markdown(
            "**" + day_label + "**" + date_label,
            unsafe_allow_html=True,
        )

    for minutes in hourly_time_slots():
        slot_end = minutes + 60
        row_columns = st.columns([0.8] + [1] * 7, gap="small")
        row_columns[0].write(format_table_time(minutes))
        for day_index, day_name in enumerate(day_names):
            selected_slot = day_name + "|" + str(minutes)
            with row_columns[day_index + 1]:
                st.button(
                    "✓" if selected_slot in preferred_time_slots else "+",
                    key="preferred_slot_" + day_name + "_" + str(minutes),
                    type="primary" if selected_slot in preferred_time_slots else "secondary",
                    width="stretch",
                    help=(
                        "取消偏好時段"
                        if selected_slot in preferred_time_slots
                        else "選取偏好時段"
                    ),
                    on_click=toggle_preferred_time_slot,
                    args=(day_name, minutes),
                )
                for event in visible_events:
                    if event["day"] != day_name:
                        continue
                    event_start = time_in_minutes(event["start"])
                    event_end = time_in_minutes(event["end"])
                    if event_start < slot_end and event_end > minutes:
                        st.markdown(
                            '<div style="background-color:'
                            + event_color(event)
                            + ';border-radius:5px;padding:4px 6px;margin:2px 0;'
                            + 'font-size:0.75rem;line-height:1.2">'
                            + "<strong>"
                            + html.escape(str(event.get("title", "未命名課程")))
                            + "</strong><br>"
                            + html.escape(str(event.get("start", "")))
                            + "-"
                            + html.escape(str(event.get("end", "")))
                            + "</div>",
                            unsafe_allow_html=True,
                        )

    st.markdown("### 匯出課表照片")
    if not calendar_valid:
        st.warning("請先設定有效的第 1 週星期一日期，再匯出課表照片。")
    else:
        image_signature = hashlib.sha256(
            json.dumps(
                {
                    "semester": semester,
                    "week_number": week_number,
                    "week_dates": [current_date.isoformat() for current_date in week_dates],
                    "events": visible_events,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        image_state_key = "calendar_image_" + semester + "_" + str(week_number)
        signature_state_key = image_state_key + "_signature"
        if st.button(
            "產生本週課表照片",
            key="generate_calendar_image_" + semester + "_" + str(week_number),
        ):
            try:
                image_bytes = render_calendar_png(
                    visible_events,
                    semester,
                    week_number,
                    week_dates,
                )
                st.session_state[image_state_key] = image_bytes
                st.session_state[signature_state_key] = image_signature
            except (OSError, ValueError) as error:
                st.error("課表照片無法產生：" + str(error))

        if st.session_state.get(signature_state_key) == image_signature:
            image_bytes = st.session_state.get(image_state_key)
            if image_bytes:
                st.image(
                    image_bytes,
                    caption="第 " + str(week_number) + " 週課表預覽",
                    width="stretch",
                )
                st.download_button(
                    "下載課表照片（PNG）",
                    data=image_bytes,
                    file_name=(
                        "課表-" + semester + "-第" + str(week_number) + "週.png"
                    ),
                    mime="image/png",
                    key="download_calendar_image_"
                    + semester
                    + "_"
                    + str(week_number),
                )

    st.markdown("### 編輯課表")
    if not visible_events:
        st.info("目前沒有課表內容，可先產生課程或加入自訂活動。")
    else:
        event_options = {}
        for event in visible_events:
            event_options[event["id"]] = (
                "星期" + event["day"] + " " + event["start"] + "-" + event["end"] + " " + event["title"]
            )

        edit_id = st.selectbox(
            "選擇要編輯的課堂",
            list(event_options.keys()),
            format_func=lambda event_id: event_options[event_id],
        )
        edit_event = None
        for event in st.session_state.schedule_events:
            if event["id"] == edit_id:
                edit_event = event

        if edit_event:
            edit_columns = st.columns(3)
            with edit_columns[0]:
                edit_title = st.text_input("課堂名稱", value=edit_event["title"], key="edit_title")
                edit_day = st.selectbox(
                    "星期",
                    day_names,
                    index=day_names.index(edit_event["day"]) if edit_event["day"] in day_names else 0,
                    key="edit_day",
                )
            with edit_columns[1]:
                edit_start = st.text_input("開始時間", value=edit_event["start"], key="edit_start")
                edit_end = st.text_input("結束時間", value=edit_event["end"], key="edit_end")
            with edit_columns[2]:
                edit_teacher = st.text_input("教師或活動主辦", value=edit_event["teacher"], key="edit_teacher")
                edit_todo = st.text_input("待辦事項", value=edit_event["todo"], key="edit_todo")
                color_widget_key = "edit_color_" + hashlib.sha256(
                    edit_id.encode("utf-8")
                ).hexdigest()[:12]
                edit_color = st.color_picker(
                    "課程顏色",
                    value=event_color(edit_event),
                    key=color_widget_key,
                )

            edit_buttons = st.columns(3)
            if edit_buttons[0].button("儲存課堂編輯"):
                if not valid_time(edit_start) or not valid_time(edit_end):
                    st.error("時間格式錯誤，請使用 09:00、13:30 等格式。")
                elif edit_start >= edit_end:
                    st.error("結束時間必須晚於開始時間。")
                else:
                    edit_event["title"] = edit_title
                    edit_event["day"] = edit_day
                    edit_event["start"] = edit_start
                    edit_event["end"] = edit_end
                    edit_event["teacher"] = edit_teacher
                    edit_event["todo"] = edit_todo
                    edit_event["color"] = edit_color
                    offering_id = edit_event.get("offering_id")
                    for event in st.session_state.schedule_events:
                        if (
                            offering_id
                            and offering_id != "CUSTOM"
                            and event.get("semester") == semester
                            and event.get("offering_id") == offering_id
                        ):
                            event["color"] = edit_color
                    save_schedule()
                    st.success("課堂已更新。")

            if edit_buttons[1].button("刪除課堂"):
                st.session_state.schedule_events = [
                    event for event in st.session_state.schedule_events
                    if event["id"] != edit_id
                ]
                save_schedule()
                st.rerun()

    st.markdown("### 新增自訂活動")
    custom_columns = st.columns(4)
    with custom_columns[0]:
        custom_title = st.text_input("活動名稱")
        custom_day = st.selectbox("活動星期", day_names)
    with custom_columns[1]:
        custom_start = st.text_input("活動開始", value="09:00")
        custom_end = st.text_input("活動結束", value="10:00")
    with custom_columns[2]:
        custom_teacher = st.text_input("備註人或主辦")
        custom_todo = st.text_input("活動待辦事項")
        custom_color = st.color_picker(
            "活動顏色",
            value=default_course_color("CUSTOM"),
            key="custom_event_color",
        )
    with custom_columns[3]:
        st.write("")
        if st.button("加入週課表"):
            if not custom_title.strip():
                st.error("請輸入活動名稱。")
            elif not valid_time(custom_start) or not valid_time(custom_end):
                st.error("時間格式錯誤，請使用 HH:MM 格式。")
            elif custom_start >= custom_end:
                st.error("結束時間必須晚於開始時間。")
            else:
                custom_id = "CUSTOM-" + str(len(st.session_state.schedule_events) + 1)
                add_event_to_schedule({
                    "id": custom_id,
                    "title": custom_title,
                    "offering_id": "CUSTOM",
                    "semester": semester,
                    "day": custom_day,
                    "start": custom_start,
                    "end": custom_end,
                    "teacher": custom_teacher or "未提供",
                    "color": custom_color,
                    "todo": custom_todo,
                    "grades": [],
                })
                st.success("活動已加入週課表。")

    st.markdown("### 考試與成績")
    if not visible_events:
        st.info("請先產生課表或加入活動，再記錄成績。")
    else:
        grade_event_options = {}
        for event in visible_events:
            grade_event_options[event["id"]] = (
                event["title"] + "｜星期" + event["day"] + " " + event["start"]
            )

        grade_event_id = st.selectbox(
            "選擇課堂記錄成績",
            list(grade_event_options.keys()),
            format_func=lambda event_id: grade_event_options[event_id],
            key="grade_event",
        )
        grade_event = None
        for event in st.session_state.schedule_events:
            if event["id"] == grade_event_id:
                grade_event = event

        if grade_event:
            if not grade_event.get("grades"):
                grade_event["grades"] = []

            grade_columns = st.columns(4)
            with grade_columns[0]:
                grade_name = st.text_input("成績項目", value="", key="grade_name")
            with grade_columns[1]:
                grade_score = st.number_input("得分", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
            with grade_columns[2]:
                grade_weight = st.number_input("占期末成績比例（%）", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
            with grade_columns[3]:
                st.write("")
                if st.button("加入成績"):
                    if not grade_name.strip():
                        st.error("請輸入成績項目名稱，例如期中考或作業一。")
                    elif grade_weight <= 0:
                        st.error("權重必須大於 0%。")
                    else:
                        grade_event["grades"].append({
                            "name": grade_name,
                            "score": grade_score,
                            "weight": grade_weight,
                        })
                        save_schedule()
                        st.success("成績已加入。")

            if grade_event["grades"]:
                st.markdown("#### 成績項目")
                for index, grade in enumerate(grade_event["grades"]):
                    grade_row = st.columns([3, 2, 2, 1])
                    grade_row[0].write(grade["name"])
                    grade_row[1].write("得分：" + str(grade["score"]))
                    grade_row[2].write("權重：" + str(grade["weight"]) + "%")
                    if grade_row[3].button("刪除", key="delete_grade_" + str(index)):
                        grade_event["grades"].pop(index)
                        save_schedule()
                        st.rerun()

                final_score, total_weight = get_event_grade(grade_event)
                st.write("已記錄權重：" + str(total_weight) + "%")
                if total_weight > 100:
                    st.warning("權重合計超過 100%，請確認各項比例。")
                if final_score is not None:
                    st.metric("目前加權期末成績", str(round(final_score, 2)) + " 分")
                    st.caption("目前成績是依已記錄項目的權重加權計算，不代表未來實際期末成績。")


def format_semester(semester):
    """把學期代碼轉成介面上容易理解的文字。"""
    if len(semester) == 4 and semester[-1] in ["1", "2"]:
        half = "上學期" if semester[-1] == "1" else "下學期"
        return semester[:3] + " 學年度" + half + "（" + semester + "）"
    return semester


def course_search_page():
    """載入資料並顯示搜尋、篩選、詳情與比較介面。"""
    st.title("中央大學選課助手 MVP")
    st.header("課程搜尋與比較")
    st.caption("課程資料來自中大官方公開查詢；本工具不取代選課系統，也不自動確認衝堂。")

    data_file = "courses.json"
    courses, error = load_menu(data_file)
    if error:
        st.error(error)
        return
    curriculum_data, curriculum_error = load_curriculum("curriculum.json")
    if not courses:
        st.warning("目前 courses.json 沒有課程資料，請先執行 python scrape_demo.py。")
        return

    semester_options = sorted(set(str(course.get("semester", "未提供")) for course in courses))
    selected_semester = st.selectbox(
        "選擇課程學期",
        semester_options,
        index=len(semester_options) - 1,
        format_func=format_semester,
    )
    term_courses = courses_for_semester(courses, selected_semester)
    term_departments = departments_for_selection(term_courses)
    general_education_units = []
    for unit, label in [
        ("核心通識課程", "核心通識"),
        ("通識教育中心", "一般通識"),
    ]:
        if any(course.get("department") == unit for course in term_courses):
            general_education_units.append(label)
    category_map = get_course_categories(curriculum_data)
    st.caption(
        "資料來源：中央大學官方公開查詢｜系所："
        + "、".join(term_departments)
        + (
            "｜通識課程："
            + "、".join(general_education_units)
            if general_education_units
            else ""
        )
        + "｜上課節次請依選課系統確認。"
    )

    st.sidebar.header("搜尋與篩選")
    keyword = st.sidebar.text_input("課名、教師或系所關鍵字")
    course_scope = st.sidebar.selectbox(
        "課程範圍",
        ["全部課程", "系所課程", "通識課程"],
    )
    available_general_categories = sorted(set(
        category_map.get(course.get("course_id"), "")
        for course in term_courses
        if course_type_label(course) != "系所課程"
        and category_map.get(course.get("course_id"), "")
    ))
    selected_general_category = st.sidebar.selectbox(
        "通識類型",
        [""] + available_general_categories,
        format_func=lambda value: value or "全部通識類型",
    )
    if not available_general_categories:
        st.sidebar.caption("目前沒有已核對的通識類型資料，課程會標示「未分類」。")
    required_options = st.sidebar.multiselect("必選修", ["必修", "選修"])
    credit_options = sorted(set(course.get("credits") for course in term_courses if isinstance(course.get("credits"), int)))
    selected_credits = st.sidebar.multiselect("學分", credit_options)

    day_options = ["一", "二", "三", "四", "五", "六", "日"]
    selected_days = st.sidebar.multiselect("上課日", day_options)
    teacher_options = sorted(set(str(course.get("teacher", "未提供")) for course in term_courses))
    selected_teachers = st.sidebar.multiselect("教師", teacher_options)

    searched = search_courses(term_courses, keyword)
    filtered = filter_courses(
        searched,
        required_options,
        selected_credits,
        selected_days,
        selected_teachers,
    )
    filtered = filter_course_scope(
        filtered,
        course_scope,
        selected_general_category,
        category_map,
    )

    st.subheader("符合條件的課程")
    st.write("共找到 " + str(len(filtered)) + " 個開課班別")
    st.caption("課程清單可在表格內捲動；選擇課程班別後，在下方查看完整資訊。")

    if not filtered:
        st.info("沒有符合條件的課程，請減少篩選條件。")
        return

    course_table = []
    for course in filtered:
        course_table.append({
            "課號": course.get("course_id", "未提供"),
            "課名": course.get("course_name", "未提供"),
            "課程類型": course_type_label(course),
            "通識類型": general_education_category_label(course, category_map),
            "教師": course.get("teacher", "未提供"),
            "選課限制": format_course_restrictions(course),
            "老師 Gmail": verified_teacher_gmail(course) or "未提供",
            "時間": format_course_time(course),
            "學分": course.get("credits", "未提供"),
        })
    st.dataframe(
        course_table,
        width="stretch",
        hide_index=True,
        height=520,
    )

    offering_names = {}
    for course in filtered:
        name = (
            str(course.get("course_name", "未提供"))
            + "｜"
            + str(course.get("teacher", "未提供"))
            + "｜"
            + str(course.get("section", "未提供"))
        )
        offering_names[course["offering_id"]] = name

    selected_offerings = st.multiselect(
        "選取要比較的課程班別",
        list(offering_names.keys()),
        format_func=lambda offering_id: offering_names[offering_id],
    )

    selected_course = st.selectbox(
        "查看課程詳情",
        filtered,
        format_func=lambda course: (
            str(course.get("course_name", "未提供"))
            + "｜"
            + str(course.get("teacher", "未提供"))
            + "｜"
            + str(course.get("section", "未提供"))
        ),
    )

    st.markdown("### 課程詳情")
    detail_columns = st.columns(2)
    with detail_columns[0]:
        st.write("課名：" + str(selected_course.get("course_name", "未提供")))
        st.write("系所：" + str(selected_course.get("department", "未提供")))
        st.write("班別：" + str(selected_course.get("section", "未提供")))
        st.write("教師：" + str(selected_course.get("teacher", "未提供")))
        st.write("課程類型：" + course_type_label(selected_course))
        st.write(
            "通識類型："
            + general_education_category_label(selected_course, category_map)
        )
        st.write("必選修：" + format_required(selected_course.get("is_required")))
        st.write("選課限制：" + format_course_restrictions(selected_course))
        show_teacher_gmail(verified_teacher_gmail(selected_course))
        st.write("學分：" + str(selected_course.get("credits", "未提供")))
    with detail_columns[1]:
        st.write(
            "上課時間："
            + format_course_time(selected_course)
        )
        st.write("官方節次與教室：" + str(selected_course.get("time", "未提供")))
        st.write("評分方式：" + str(selected_course.get("grading", "未提供")))
        st.write("教學風格：" + str(selected_course.get("teaching_style", "未提供")))
        reviews = selected_course.get("reviews", [])
        if reviews:
            st.write("修課心得：")
            for review in reviews:
                st.write("- " + str(review))
        else:
            st.write("修課心得：未提供")

    st.markdown("#### 資料來源")
    show_sources(selected_course.get("sources", []))

    st.markdown("## 並排比較")
    if not selected_offerings:
        st.info("請在上方選取至少兩門課程班別來並排比較。")
        return

    selected_courses = compare_courses(term_courses, selected_offerings, category_map)
    compare_columns = st.columns(len(selected_courses))
    for index, course in enumerate(selected_courses):
        with compare_columns[index]:
            st.markdown("### " + str(course["course_name"]))
            st.write("班別：" + str(course["section"]))
            st.write("教師：" + str(course["teacher"]))
            st.write("選課限制：" + format_course_restrictions(course))
            show_teacher_gmail(course.get("teacher_gmail", ""))
            st.write("課程類型：" + str(course["course_type"]))
            st.write("通識類型：" + str(course["general_education_category"]))
            st.write("必選修：" + format_required(course["is_required"]))
            st.write("學分：" + str(course["credits"]))
            st.write("上課時間：" + format_course_time(course))
            st.write("官方節次與教室：" + str(course.get("official_time", "未提供")))
            st.write("評分方式：" + str(course["grading"]))
            st.write("教學風格：" + str(course["teaching_style"]))
            st.write("修課心得：")
            if course["reviews"]:
                for review in course["reviews"]:
                    st.write("- " + str(review))
            else:
                st.write("未提供")
            st.markdown("**資料來源**")
            show_sources(course["sources"])

    st.markdown("## AI 比較摘要")
    st.caption("摘要僅會使用下方已選課程的欄位與來源，不會傳送姓名、學號或個人資料。")
    if st.button("整理差異"):
        summary, summary_error = summarize_comparison(selected_courses)
        if summary_error:
            st.error(summary_error)
        else:
            st.success("以下摘要由 AI 產生：")
            st.write(summary)


def home_page(navigation_pages):
    """顯示首頁摘要與主要功能入口。"""
    st.title("首頁")
    st.subheader("中央大學選課助手")
    st.write("從個人條件開始，整理課程、建立願望清單，再規劃你的課表。")

    courses, course_error = load_menu("courses.json")
    if course_error:
        st.error(course_error)
        return
    profile, profile_error = load_user_profile("course_profile.json")
    workspace, workspace_error = load_course_workspace("course_workspace.json")
    if profile_error:
        st.error(profile_error)
    if workspace_error:
        st.error(workspace_error)
    if profile_error or workspace_error:
        return
    if not courses:
        st.warning("目前沒有課程資料，請先準備 courses.json。")
        return

    semesters = sorted(set(str(course.get("semester", "未提供")) for course in courses))
    semester = st.selectbox(
        "目前規劃學期",
        semesters,
        index=len(semesters) - 1,
        format_func=format_semester,
        key="home_semester",
    )
    semester_courses = courses_for_semester(courses, semester)
    confirmed_count = len(workspace.get("confirmed", []))
    profile_department = profile.get("department") or "尚未設定系所"
    profile_grade = profile.get("grade") or "尚未設定年級"

    summary_columns = st.columns(3)
    summary_columns[0].metric("本學期課程", len(semester_courses))
    summary_columns[1].metric("願望清單課程", confirmed_count)
    summary_columns[2].metric("目前個人檔案", profile_department + "｜" + profile_grade)

    st.markdown("## 開始使用")
    entry_columns = st.columns(2)
    with entry_columns[0]:
        st.subheader("AI 幫忙排課")
        st.caption("設定條件、比較推薦課表，再與 AI 討論修課安排。")
        st.page_link(
            navigation_pages["planner"],
            label="前往 AI 幫忙排課",
            icon="🗓️",
        )
        st.subheader("課程搜尋與比較")
        st.caption("搜尋課程資訊、查看來源並排比較。")
        st.page_link(
            navigation_pages["search"],
            label="前往課程搜尋與比較",
            icon="🔎",
        )
    with entry_columns[1]:
        st.subheader("個人檔案")
        st.caption("儲存系級、已修課、學分目標與時間偏好。")
        st.page_link(
            navigation_pages["profile"],
            label="編輯個人檔案",
            icon="👤",
        )
        st.subheader("選課願望清單")
        st.caption("管理已確定課程和每門課的筆記附件。")
        st.page_link(
            navigation_pages["wishlist"],
            label="查看選課願望清單",
            icon="📚",
        )

    st.info(
        "也可使用左側選單切換頁面。個人條件、願望清單、筆記與附件"
        "保存在本機，不會傳送給 AI。"
    )


def main():
    """建立頁面選單並執行目前選取的頁面。"""
    st.set_page_config(
        page_title="中央大學選課助手",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    navigation_pages = {}

    def render_home():
        home_page(navigation_pages)

    navigation_pages["home"] = st.Page(
        render_home,
        title="首頁",
        icon=":material/home:",
        default=True,
    )
    navigation_pages["profile"] = st.Page(
        "pages/個人檔案.py",
        title="個人檔案",
        icon=":material/person:",
    )
    navigation_pages["wishlist"] = st.Page(
        "pages/選課願望清單.py",
        title="選課願望清單",
        icon=":material/bookmark:",
    )
    navigation_pages["planner"] = st.Page(
        "pages/AI_幫忙排課.py",
        title="AI 幫忙排課",
        icon=":material/calendar_month:",
    )
    navigation_pages["search"] = st.Page(
        "pages/課程搜尋與比較.py",
        title="課程搜尋與比較",
        icon=":material/search:",
    )
    selected_page = st.navigation(
        list(navigation_pages.values()),
        position="sidebar",
        expanded=True,
    )
    selected_page.run()


if __name__ == "__main__":
    main()
