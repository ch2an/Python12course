import streamlit as st

from app import (
    UNDERGRADUATE_YEAR_OPTIONS,
    courses_for_semester,
    departments_for_selection,
    format_preferred_time_slots,
    format_semester,
    hourly_time_slots,
    load_menu,
)
from course_workspace import load_user_profile, save_user_profile


st.title("個人檔案")
st.caption("這些設定只用於課程推薦與 AI 對話；不需要填姓名或學號。")

courses, course_error = load_menu("courses.json")
if course_error:
    st.error(course_error)
    st.stop()
profile, profile_error = load_user_profile("course_profile.json")
if profile_error:
    st.error(profile_error)
    st.stop()

semesters = sorted(set(str(course.get("semester", "未提供")) for course in courses))
if semesters:
    semester = st.selectbox(
        "課程學期",
        semesters,
        index=len(semesters) - 1,
        format_func=format_semester,
        key="profile_semester",
    )
    term_courses = courses_for_semester(courses, semester)
else:
    term_courses = courses
departments = departments_for_selection(term_courses)
saved_department = profile.get("department", "")
if saved_department and saved_department not in departments:
    departments.insert(0, saved_department)
slot_options = [
    day + "|" + str(start)
    for day in ["一", "二", "三", "四", "五", "六", "日"]
    for start in hourly_time_slots()
]
profile_defaults = {
    "profile_department": saved_department,
    "profile_grade": profile.get("grade", ""),
    "profile_required_courses": profile.get("department_requirements", ""),
    "profile_completed_courses": profile.get("completed_courses", ""),
    "profile_interests": profile.get("interests", ""),
    "profile_target_credits": profile.get("target_credits", 0),
    "profile_maximum_credits": profile.get("maximum_credits", 0),
    "profile_unavailable_times": profile.get("unavailable_times", ""),
    "profile_workload": profile.get("workload", "未指定"),
    "profile_preferred_days": profile.get("preferred_days", []),
    "profile_preferred_time_slots": profile.get("preferred_time_slots", []),
}
for key, value in profile_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value
for key in ["profile_target_credits", "profile_maximum_credits"]:
    if not isinstance(st.session_state[key], int):
        st.session_state[key] = 0
    st.session_state[key] = min(max(st.session_state[key], 0), 30)
department_options = [""] + departments
if st.session_state["profile_department"] not in department_options:
    st.session_state["profile_department"] = ""
if st.session_state["profile_grade"] not in [""] + UNDERGRADUATE_YEAR_OPTIONS:
    st.session_state["profile_grade"] = ""
if st.session_state["profile_workload"] not in ["未指定", "輕量", "中等", "挑戰"]:
    st.session_state["profile_workload"] = "未指定"
st.session_state["profile_preferred_days"] = [
    day
    for day in st.session_state["profile_preferred_days"]
    if day in ["一", "二", "三", "四", "五", "六", "日"]
]
st.session_state["profile_preferred_time_slots"] = [
    slot
    for slot in st.session_state["profile_preferred_time_slots"]
    if slot in slot_options
]

department = st.selectbox(
    "系所或學位學程",
    department_options,
    format_func=lambda value: value or "請選擇系所",
    key="profile_department",
)
grade_options = [""] + UNDERGRADUATE_YEAR_OPTIONS
grade = st.selectbox(
    "年級",
    grade_options,
    format_func=lambda value: value or "請選擇年級",
    key="profile_grade",
)

profile_columns = st.columns(2)
with profile_columns[0]:
    required_courses = st.text_area(
        "系級或畢業必修",
        key="profile_required_courses",
        help="可輸入課名或課號，以逗號分隔。",
    )
    completed_courses = st.text_area(
        "已修課程",
        key="profile_completed_courses",
        help="用來避免推薦已修過的課程；可用逗號分隔。",
    )
    interests = st.text_input(
        "興趣或學習需求",
        key="profile_interests",
    )
with profile_columns[1]:
    target_credits = st.number_input(
        "本學期想修學分",
        min_value=0,
        max_value=30,
        step=1,
        key="profile_target_credits",
    )
    maximum_credits = st.number_input(
        "可接受學分上限",
        min_value=0,
        max_value=30,
        step=1,
        key="profile_maximum_credits",
    )
    unavailable_times = st.text_area(
        "不能上課的時間",
        key="profile_unavailable_times",
        help="例如：星期三下午、星期五 10:00–12:00。",
    )
    workload_options = ["未指定", "輕量", "中等", "挑戰"]
    workload = st.selectbox(
        "想要的課業負荷",
        workload_options,
        key="profile_workload",
    )

st.markdown("## 上課偏好")
day_options = ["一", "二", "三", "四", "五", "六", "日"]
preferred_days = st.multiselect(
    "偏好的上課日",
    day_options,
    key="profile_preferred_days",
)
preferred_time_slots = st.multiselect(
    "偏好的上課時段（每格一小時）",
    slot_options,
    format_func=lambda slot: format_preferred_time_slots([slot])[0],
    key="profile_preferred_time_slots",
)

if st.button("儲存個人檔案", type="primary"):
    updated_profile = {
        "department": department,
        "grade": grade,
        "department_requirements": required_courses,
        "completed_courses": completed_courses,
        "interests": interests,
        "target_credits": target_credits,
        "maximum_credits": maximum_credits,
        "unavailable_times": unavailable_times,
        "workload": workload,
        "preferred_days": preferred_days,
        "preferred_time_slots": preferred_time_slots,
    }
    save_error = save_user_profile(updated_profile, "course_profile.json")
    if save_error:
        st.error(save_error)
    else:
        st.success("個人檔案已儲存在本機。")
