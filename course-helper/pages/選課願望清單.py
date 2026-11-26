import hashlib

import streamlit as st

from app import (
    courses_for_semester,
    format_course_time,
    format_semester,
    load_menu,
)
from course_workspace import load_course_workspace, save_course_workspace


st.title("選課願望清單")
st.caption("整理已確定要修的課程；課程筆記與附件只保存在本機。")

courses, course_error = load_menu("courses.json")
if course_error:
    st.error(course_error)
    st.stop()
workspace, workspace_error = load_course_workspace("course_workspace.json")
if workspace_error:
    st.error(workspace_error)
    st.stop()

semesters = sorted(set(str(course.get("semester", "未提供")) for course in courses))
if not semesters:
    st.info("目前沒有課程資料。")
    st.stop()
semester = st.selectbox(
    "課程學期",
    semesters,
    index=len(semesters) - 1,
    format_func=format_semester,
    key="wishlist_semester",
)
term_courses = courses_for_semester(courses, semester)


def workspace_key(course):
    return semester + "::" + str(course.get("offering_id", ""))


course_by_key = {workspace_key(course): course for course in term_courses}
confirmed_keys = [
    key for key in workspace["confirmed"] if key in course_by_key
]
available_courses = [
    course
    for course in term_courses
    if workspace_key(course) not in workspace["confirmed"]
]
course_options = {
    workspace_key(course): (
        str(course.get("course_name", "未提供"))
        + "｜"
        + str(course.get("section", "未提供"))
        + "｜"
        + str(course.get("teacher", "未提供"))
    )
    for course in available_courses
}
selected_course_key = st.selectbox(
    "加入課程",
    [""] + list(course_options),
    format_func=lambda key: course_options.get(key, "選擇課程班別"),
    key="wishlist_add_course",
    disabled=not course_options,
)
if st.button("加入願望清單", disabled=not selected_course_key):
    workspace["confirmed"].append(selected_course_key)
    workspace["notes"].setdefault(
        selected_course_key,
        {"text": "", "attachments": []},
    )
    save_error = save_course_workspace(workspace, "course_workspace.json")
    if save_error:
        st.error(save_error)
    else:
        st.rerun()

st.write("目前清單有 " + str(len(confirmed_keys)) + " 門課。")
if not confirmed_keys:
    st.info("尚未加入課程。可從上方新增，也可以在 AI 排課頁加入推薦課表。")
else:
    st.caption("照片與錄音可在左側選單的「AI 幫忙排課」頁新增或管理。")

for key in confirmed_keys:
    course = course_by_key[key]
    note = workspace["notes"].setdefault(key, {"text": "", "attachments": []})
    widget_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    with st.container(border=True):
        title_columns = st.columns([5, 1])
        with title_columns[0]:
            st.subheader(
                str(course.get("course_name", "未提供"))
                + "｜"
                + str(course.get("section", "未提供"))
            )
            st.caption(
                str(course.get("course_id", "未提供"))
                + "｜"
                + str(course.get("teacher", "未提供"))
                + "｜"
                + format_course_time(course)
            )
        with title_columns[1]:
            if st.button("移除", key="wishlist_remove_" + widget_id):
                workspace["confirmed"].remove(key)
                save_error = save_course_workspace(
                    workspace,
                    "course_workspace.json",
                )
                if save_error:
                    st.error(save_error)
                else:
                    st.rerun()

        note_key = "wishlist_note_" + widget_id
        if note_key not in st.session_state:
            st.session_state[note_key] = note.get("text", "")
        st.text_area(
            "課程筆記",
            key=note_key,
            placeholder="記錄想問老師的問題、課程重點或自己的備註。",
        )
        if st.button("儲存筆記", key="wishlist_save_note_" + widget_id):
            ai_note_key = "course_note_text_" + widget_id
            if ai_note_key in st.session_state:
                st.session_state[ai_note_key] = st.session_state[note_key]
            workspace["notes"][key] = {
                "text": st.session_state[note_key],
                "attachments": note.get("attachments", []),
            }
            save_error = save_course_workspace(
                workspace,
                "course_workspace.json",
            )
            if save_error:
                st.error(save_error)
            else:
                st.success("筆記已儲存在本機。")

        if note.get("attachments"):
            st.caption(
                "已存 "
                + str(len(note["attachments"]))
                + " 個照片或錄音；可在 AI 排課頁播放或下載。"
            )
