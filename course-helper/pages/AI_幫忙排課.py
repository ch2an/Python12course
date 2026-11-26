import hashlib
import json
from pathlib import Path

import streamlit as st

from app import (
    UNDERGRADUATE_YEAR_OPTIONS,
    apply_schedule_plan,
    courses_for_recommendation,
    courses_for_semester,
    departments_for_selection,
    find_curriculum,
    format_course_restrictions,
    format_course_time,
    format_preferred_time_slots,
    format_semester,
    general_education_category_label,
    get_course_categories,
    hourly_time_slots,
    load_curriculum,
    load_menu,
    recommend_schedules,
    show_week_calendar,
    verified_teacher_gmail,
    chat_schedule,
)
from course_workspace import (
    load_course_workspace,
    load_user_profile,
    save_course_workspace,
    save_media_upload,
    save_user_profile,
)


st.title("AI 幫忙排課")
st.caption(
    "設定系級、學分和偏好，查看多套推薦並與 AI 討論；"
    "課表草案仍須到官方選課系統確認時間與衝堂。"
)

courses, error = load_menu("courses.json")
if error:
    st.error(error)
    st.stop()
curriculum_data, curriculum_error = load_curriculum("curriculum.json")
if not courses:
    st.warning("目前 courses.json 沒有課程資料，請先執行 python scrape_demo.py。")
    st.stop()

semester_options = sorted(
    set(str(course.get("semester", "未提供")) for course in courses)
)
selected_semester = st.selectbox(
    "選擇課程學期",
    semester_options,
    index=len(semester_options) - 1,
    format_func=format_semester,
    key="planner_semester",
)
term_courses = courses_for_semester(courses, selected_semester)
departments = departments_for_selection(term_courses)
category_map = get_course_categories(curriculum_data)
workspace_path = Path("course_workspace.json")
media_directory = Path("course_workspace_media")
workspace, workspace_error = load_course_workspace(workspace_path)
if workspace_error:
    st.sidebar.error(workspace_error)
    st.stop()
profile_data, profile_error = load_user_profile("course_profile.json")
if profile_error:
    st.error(profile_error)
    st.stop()
saved_department = profile_data.get("department", "")
if saved_department and saved_department not in departments:
    departments.append(saved_department)

profile_defaults = {
    "planner_department": profile_data.get("department", ""),
    "planner_grade": profile_data.get("grade", ""),
    "planner_required_courses": profile_data.get("department_requirements", ""),
    "planner_completed_courses": profile_data.get("completed_courses", ""),
    "planner_target_credits": profile_data.get("target_credits", 0),
    "planner_maximum_credits": profile_data.get("maximum_credits", 0),
    "planner_unavailable_times": profile_data.get("unavailable_times", ""),
    "planner_workload": profile_data.get("workload", "未指定"),
    "planner_interests": profile_data.get("interests", ""),
    "preferred_days": profile_data.get("preferred_days", []),
    "preferred_time_slots": profile_data.get("preferred_time_slots", []),
}
profile_signature = json.dumps(profile_data, ensure_ascii=False, sort_keys=True)
profile_changed = (
    st.session_state.get("_planner_profile_signature") != profile_signature
)
for key, value in profile_defaults.items():
    if profile_changed or key not in st.session_state:
        st.session_state[key] = value
st.session_state["_planner_profile_signature"] = profile_signature
for key in ["planner_target_credits", "planner_maximum_credits"]:
    if not isinstance(st.session_state[key], int):
        st.session_state[key] = 0
    st.session_state[key] = min(max(st.session_state[key], 0), 30)
if st.session_state["planner_department"] not in [""] + departments:
    st.session_state["planner_department"] = ""
if st.session_state["planner_grade"] not in [""] + UNDERGRADUATE_YEAR_OPTIONS:
    st.session_state["planner_grade"] = ""
if st.session_state["planner_workload"] not in ["未指定", "輕量", "中等", "挑戰"]:
    st.session_state["planner_workload"] = "未指定"
valid_days = ["一", "二", "三", "四", "五", "六", "日"]
valid_time_slots = {
    day + "|" + str(start)
    for day in valid_days
    for start in hourly_time_slots()
}
st.session_state["preferred_days"] = [
    day for day in st.session_state["preferred_days"] if day in valid_days
]
st.session_state["preferred_time_slots"] = [
    slot
    for slot in st.session_state["preferred_time_slots"]
    if slot in valid_time_slots
]


def workspace_course_key(course):
    return selected_semester + "::" + str(course.get("offering_id", ""))


course_by_workspace_key = {
    workspace_course_key(course): course for course in term_courses
}
confirmed_course_keys = [
    key for key in workspace["confirmed"] if key in course_by_workspace_key
]

with st.sidebar:
    st.header("工作欄｜已確定課程")
    available_to_confirm = [
        course
        for course in term_courses
        if workspace_course_key(course) not in workspace["confirmed"]
    ]
    course_options = {
        workspace_course_key(course): (
            str(course.get("course_name", "未提供"))
            + "｜"
            + str(course.get("section", "未提供"))
        )
        for course in available_to_confirm
    }
    selected_to_confirm = st.selectbox(
        "加入已確定課程",
        [""] + list(course_options),
        format_func=lambda key: course_options.get(key, "選擇課程班別"),
        key="workspace_course_to_add",
        disabled=not course_options,
    )
    if st.button(
        "加入工作欄",
        key="workspace_add_course",
        disabled=not selected_to_confirm,
    ):
        workspace["confirmed"].append(selected_to_confirm)
        workspace["notes"].setdefault(
            selected_to_confirm,
            {"text": "", "attachments": []},
        )
        save_error = save_course_workspace(workspace, workspace_path)
        if save_error:
            st.error(save_error)
        else:
            st.rerun()

    st.caption("文字、照片和錄音只儲存在本機，不會傳送給 AI。")
    if not confirmed_course_keys:
        st.info("加入確定要修的課程後，便可在每門課下記錄筆記。")

    for confirmed_key in confirmed_course_keys:
        course = course_by_workspace_key[confirmed_key]
        course_label = (
            str(course.get("course_name", "未提供"))
            + "｜"
            + str(course.get("section", "未提供"))
        )
        widget_id = hashlib.sha256(confirmed_key.encode("utf-8")).hexdigest()[:12]
        note = workspace["notes"].setdefault(
            confirmed_key,
            {"text": "", "attachments": []},
        )
        with st.expander(course_label, expanded=False):
            st.caption(
                str(course.get("teacher", "未提供"))
                + "｜"
                + format_course_time(course)
            )
            note_widget_key = "course_note_text_" + widget_id
            if note_widget_key not in st.session_state:
                st.session_state[note_widget_key] = note.get("text", "")
            st.text_area(
                "課程筆記",
                key=note_widget_key,
                height=120,
            )
            camera_photo = st.camera_input(
                "拍攝課堂照片",
                key="course_note_camera_" + widget_id,
            )
            uploaded_photos = st.file_uploader(
                "上傳照片",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                max_upload_size=10,
                key="course_note_photos_" + widget_id,
            )
            recorded_audio = st.audio_input(
                "錄音",
                sample_rate=16000,
                key="course_note_audio_" + widget_id,
            )

            for attachment in note.get("attachments", []):
                filename = attachment.get("file", "")
                if Path(filename).name != filename:
                    st.warning("附件檔名不正確，無法顯示。")
                    continue
                attachment_path = media_directory / filename
                if not attachment_path.is_file():
                    st.warning("找不到已儲存的附件：" + attachment.get("name", "附件"))
                    continue
                content = attachment_path.read_bytes()
                mime_type = attachment.get("mime_type", "")
                if mime_type.startswith("image/"):
                    st.image(content, caption=attachment.get("name", "課程照片"))
                elif mime_type.startswith("audio/"):
                    st.audio(content, format=mime_type)
                st.download_button(
                    "下載 " + attachment.get("name", "附件"),
                    content,
                    file_name=attachment.get("name", "附件"),
                    mime=mime_type or "application/octet-stream",
                    key="course_note_download_" + widget_id + "_" + filename,
                )

            if st.button("儲存筆記與附件", key="course_note_save_" + widget_id):
                new_uploads = []
                if camera_photo is not None:
                    new_uploads.append(camera_photo)
                new_uploads.extend(uploaded_photos or [])
                if recorded_audio is not None:
                    new_uploads.append(recorded_audio)
                attachments = list(note.get("attachments", []))
                upload_errors = []
                added_count = 0
                duplicate_count = 0
                for upload in new_uploads:
                    saved_attachment, duplicated, upload_error = save_media_upload(
                        upload.getvalue(),
                        upload.name,
                        upload.type,
                        media_directory,
                        attachments,
                    )
                    if upload_error:
                        upload_errors.append(upload_error)
                    elif duplicated:
                        duplicate_count += 1
                    elif saved_attachment:
                        attachments.append(saved_attachment)
                        added_count += 1
                workspace["notes"][confirmed_key] = {
                    "text": st.session_state[note_widget_key],
                    "attachments": attachments,
                }
                wishlist_note_key = "wishlist_note_" + widget_id
                if wishlist_note_key in st.session_state:
                    st.session_state[wishlist_note_key] = st.session_state[
                        note_widget_key
                    ]
                save_error = save_course_workspace(workspace, workspace_path)
                if save_error:
                    st.error(save_error)
                else:
                    if upload_errors:
                        st.warning("部分附件未儲存：" + "；".join(upload_errors))
                    st.success(
                        "筆記已儲存；新增 "
                        + str(added_count)
                        + " 個附件，略過重複附件 "
                        + str(duplicate_count)
                        + " 個。"
                    )
                    st.rerun()

            if st.button(
                "從工作欄移除",
                key="course_note_remove_" + widget_id,
            ):
                workspace["confirmed"].remove(confirmed_key)
                save_error = save_course_workspace(workspace, workspace_path)
                if save_error:
                    st.error(save_error)
                else:
                    st.rerun()

if curriculum_error:
    st.warning(curriculum_error)

st.markdown("## 設定你的選課條件")
profile_columns = st.columns(3)
with profile_columns[0]:
    department = st.selectbox(
        "系所或學位學程",
        [""] + departments,
        format_func=lambda value: value or "請選擇系所或不指定",
        key="planner_department",
    )
    grade = st.selectbox(
        "年級",
        [""] + UNDERGRADUATE_YEAR_OPTIONS,
        format_func=lambda value: value or "請選擇年級（可留空）",
        key="planner_grade",
    )
    required_courses = st.text_input(
        "系級或畢業必修（可用逗號分隔）",
        key="planner_required_courses",
    )
with profile_columns[1]:
    completed_courses = st.text_input(
        "已修課程（可用逗號分隔）",
        key="planner_completed_courses",
    )
    target_credits = st.number_input(
        "本學期想修學分",
        min_value=0,
        max_value=30,
        step=1,
        key="planner_target_credits",
    )
    maximum_credits = st.number_input(
        "可接受學分上限",
        min_value=0,
        max_value=30,
        step=1,
        key="planner_maximum_credits",
    )
with profile_columns[2]:
    unavailable_times = st.text_area(
        "不能上課的時間",
        key="planner_unavailable_times",
    )
    workload = st.selectbox(
        "想要的課業負荷",
        ["未指定", "輕量", "中等", "挑戰"],
        key="planner_workload",
    )
    preferred_days = st.session_state.get("preferred_days", [])
    preferred_time_slots = st.session_state.get("preferred_time_slots", [])
    st.caption(
        "偏好上課日與時段可在下方「我的週課表與偏好時段」直接點選。"
    )
    st.write(
        "目前偏好上課日："
        + ("、".join(preferred_days) if preferred_days else "未指定")
    )
    formatted_preferred_time_slots = format_preferred_time_slots(
        preferred_time_slots
    )
    st.write(
        "目前偏好時段："
        + (
            "、".join(formatted_preferred_time_slots)
            if formatted_preferred_time_slots
            else "未指定"
        )
    )

curriculum_record = find_curriculum(
    curriculum_data,
    department,
    grade,
    selected_semester,
)
if curriculum_record:
    st.success("已載入符合系所、年級和學期的人工核對課程地圖。")
elif department:
    st.warning(
        "找不到這個系級與學期的課程地圖；推薦只會使用所選系所的開課資料，"
        "不代表系級必修或畢業規定。"
    )
else:
    st.info("可先選擇系所與年級；未指定系所時會依本學期所有課程推薦。")

recommendation_courses = courses_for_recommendation(
    term_courses,
    department,
    curriculum_record,
)
if not any(
    course.get("target_year")
    and course.get("target_year") != "未提供"
    for course in recommendation_courses
):
    st.info(
        "目前課程資料沒有適用年級標記；年級會提供給 AI 作為背景，"
        "但不會用來篩選課程。"
    )

available_categories = sorted(
    set(
        category_map.get(course.get("course_id"), "")
        for course in recommendation_courses
        if category_map.get(course.get("course_id"), "")
    )
)
selected_categories = []
if available_categories:
    selected_categories = st.multiselect(
        "優先推薦的官方通識類別",
        available_categories,
        key="planner_categories",
    )
else:
    st.info("目前資料沒有經核對的官方通識分類；不會依課號推測分類。")

recommendation_columns = st.columns(2)
with recommendation_columns[0]:
    interests_text = st.text_input(
        "興趣或需求（以逗號分隔）",
        key="planner_interests",
    )
with recommendation_columns[1]:
    option_count = st.selectbox(
        "要產生幾套課表方案",
        [2, 3, 4, 5],
        index=1,
        key="planner_option_count",
    )

interests = [
    interest.strip()
    for interest in interests_text.replace("，", ",").replace("、", ",").split(",")
    if interest.strip()
]
schedules, missing_required = recommend_schedules(
    recommendation_courses,
    curriculum_record,
    interests,
    target_credits,
    maximum_credits,
    option_count,
    selected_categories,
    category_map,
    preferred_days,
    preferred_time_slots,
)
if missing_required:
    st.warning(
        "課程地圖列出的必修課目前不在所選學期資料中，未納入方案："
        + "、".join(missing_required)
    )
if len(schedules) < option_count:
    st.info("目前可用課程有限，僅產生 " + str(len(schedules)) + " 套不同方案。")

if schedules:
    st.markdown("## 推薦課表")
    plan_tabs = st.tabs(
        ["方案 " + str(index + 1) for index in range(len(schedules))]
    )
    for plan_index, plan_tab in enumerate(plan_tabs):
        with plan_tab:
            plan = schedules[plan_index]
            selected_plan_courses = []
            for course_index, recommended_course in enumerate(plan["courses"]):
                course_id = recommended_course.get("course_id")
                is_required = bool(
                    curriculum_record
                    and course_id
                    in curriculum_record.get("required_course_ids", [])
                )
                course_category = category_map.get(course_id, "")
                replacement_options = []
                for candidate in recommendation_courses:
                    if is_required and candidate.get("course_id") != course_id:
                        continue
                    if (
                        not is_required
                        and course_category
                        and category_map.get(candidate.get("course_id"), "")
                        != course_category
                    ):
                        continue
                    replacement_options.append(candidate)
                if not replacement_options:
                    replacement_options = [recommended_course]

                replacement_ids = [
                    course.get("offering_id") for course in replacement_options
                ]
                current_id = recommended_course.get("offering_id")
                if current_id not in replacement_ids:
                    replacement_options.insert(0, recommended_course)
                    replacement_ids.insert(0, current_id)
                selected_id = st.selectbox(
                    "課程 " + str(course_index + 1) + "（可替換）",
                    replacement_ids,
                    index=replacement_ids.index(current_id),
                    format_func=lambda offering_id, choices=replacement_options: next(
                        (
                            str(course.get("course_name", "未提供"))
                            + "｜"
                            + str(course.get("teacher", "未提供"))
                            + "｜"
                            + str(course.get("section", "未提供"))
                            + "｜"
                            + format_course_restrictions(course)
                            + "｜Gmail："
                            + (verified_teacher_gmail(course) or "未提供")
                            for course in choices
                            if course.get("offering_id") == offering_id
                        ),
                        offering_id,
                    ),
                    key=(
                        "planner_recommendation_"
                        + selected_semester
                        + "_"
                        + str(plan_index)
                        + "_"
                        + str(course_index)
                    ),
                )
                selected_course = next(
                    course
                    for course in replacement_options
                    if course.get("offering_id") == selected_id
                )
                selected_plan_courses.append(selected_course)
                st.caption(
                    str(selected_course.get("course_id", "未提供"))
                    + "｜"
                    + str(selected_course.get("credits", "未提供"))
                    + " 學分｜"
                    + general_education_category_label(
                        selected_course, category_map
                    )
                    + "｜Gmail："
                    + (verified_teacher_gmail(selected_course) or "未提供")
                    + "｜時間："
                    + format_course_time(selected_course)
                )

            total_credits = sum(
                course.get("credits", 0)
                for course in selected_plan_courses
                if isinstance(course.get("credits"), (int, float))
            )
            st.caption("目前方案共 " + str(total_credits) + " 學分。")
            if selected_plan_courses and st.button(
                "以此方案取代本學期週課表",
                key="apply_planner_recommendation_" + str(plan_index),
                help="會替換本學期已排入的課程並保留自訂活動；缺少鐘點的方案不會套用。",
            ):
                applied, missing_times, duplicate_course_ids = apply_schedule_plan(
                    selected_plan_courses,
                    selected_semester,
                )
                if applied:
                    for selected_course in selected_plan_courses:
                        confirmed_key = workspace_course_key(selected_course)
                        if confirmed_key not in workspace["confirmed"]:
                            workspace["confirmed"].append(confirmed_key)
                        workspace["notes"].setdefault(
                            confirmed_key,
                            {"text": "", "attachments": []},
                        )
                    workspace_error = save_course_workspace(
                        workspace,
                        workspace_path,
                    )
                    if workspace_error:
                        st.error(
                            "課表已更新，但已確定課程清單未能儲存："
                            + workspace_error
                        )
                    else:
                        st.session_state.schedule_plan_notice = (
                            "已將方案 "
                            + str(plan_index + 1)
                            + " 加入週課表，並放入左側工作欄。"
                        )
                        st.rerun()
                if missing_times:
                    st.warning(
                        "方案中有課程缺少已確認的 HH:MM 時間，未更動週課表："
                        + "、".join(missing_times)
                    )
                elif duplicate_course_ids:
                    st.warning(
                        "方案含重複課號，未更動週課表："
                        + "、".join(duplicate_course_ids)
                    )
                elif not applied:
                    st.error("週課表無法保存；原課表已保留。")
else:
    st.info("目前資料不足以組成課表方案；請調整條件或補充本學期課程資料。")

profile = {
    "department": department or "未提供",
    "grade": grade or "未提供",
    "department_requirements": required_courses or "未提供",
    "completed_courses": completed_courses or "未提供",
    "target_credits": target_credits,
    "maximum_credits": maximum_credits,
    "unavailable_times": unavailable_times or "未提供",
    "preferred_days": preferred_days,
    "preferred_time_slots": formatted_preferred_time_slots,
    "workload": workload,
}

if st.button("儲存這些條件至個人檔案", key="save_planner_profile"):
    profile_to_save = dict(profile)
    profile_to_save["interests"] = interests_text
    save_error = save_user_profile(profile_to_save, "course_profile.json")
    if save_error:
        st.error(save_error)
    else:
        st.success("選課條件已儲存在個人檔案。")

st.markdown("## 與 AI 討論課表")
st.caption("可補充系級必修、已修課、時間限制、老師偏好或課業負荷等需求。")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
for chat in st.session_state.chat_history:
    with st.chat_message(chat["role"]):
        st.markdown(chat["content"])

question = st.chat_input(
    "例如：我是大二資工系，想修必修但避免星期一下午，可以建議一份課表嗎？"
)
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("正在依課程資料整理課表草案..."):
            answer, chat_error = chat_schedule(
                profile,
                question,
                term_courses,
                st.session_state.chat_history[:-1],
            )
        if chat_error:
            st.error(chat_error)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": chat_error}
            )
        else:
            st.markdown(answer)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": answer}
            )

with st.expander("我的週課表與偏好時段", expanded=False):
    show_week_calendar(term_courses, selected_semester, curriculum_data)
