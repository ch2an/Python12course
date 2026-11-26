import hashlib
import json
import os
import uuid
from datetime import date
from pathlib import Path


MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 20 * 1024 * 1024


def empty_course_workspace():
    return {"confirmed": [], "notes": {}, "week_one_mondays": {}}


def load_user_profile(file_path):
    """讀取本機個人選課設定。"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}, ""
    except json.JSONDecodeError as error:
        return {}, "個人檔案 JSON 格式錯誤：" + str(error)
    except OSError as error:
        return {}, "讀取個人檔案失敗：" + str(error)
    if not isinstance(data, dict):
        return {}, "個人檔案格式錯誤：最外層應為 JSON 物件。"
    text_fields = [
        "department",
        "grade",
        "department_requirements",
        "completed_courses",
        "interests",
        "unavailable_times",
        "workload",
    ]
    for field in text_fields:
        if field in data and not isinstance(data[field], str):
            return {}, "個人檔案格式錯誤：" + field + " 應為文字。"
    for field in ["preferred_days", "preferred_time_slots"]:
        values = data.get(field, [])
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            return {}, "個人檔案格式錯誤：" + field + " 應為文字陣列。"
    for field in ["target_credits", "maximum_credits"]:
        value = data.get(field, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return {}, "個人檔案格式錯誤：" + field + " 應為非負整數。"
    return data, ""


def save_user_profile(profile, file_path):
    """以暫存檔取代個人檔案 JSON。"""
    temporary_path = str(file_path) + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(profile, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, file_path)
        return ""
    except OSError as error:
        return "儲存個人檔案失敗：" + str(error)


def load_course_workspace(file_path):
    """讀取已確定課程與私人筆記；資料格式錯誤時回報訊息。"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return empty_course_workspace(), ""
    except json.JSONDecodeError as error:
        return {}, "課程工作區 JSON 格式錯誤：" + str(error)
    except OSError as error:
        return {}, "讀取課程工作區失敗：" + str(error)

    if not isinstance(data, dict):
        return {}, "課程工作區格式錯誤：最外層應為 JSON 物件。"
    confirmed = data.get("confirmed", [])
    notes = data.get("notes", {})
    week_one_mondays = data.get("week_one_mondays", {})
    if not isinstance(confirmed, list) or not all(
        isinstance(key, str) for key in confirmed
    ):
        return {}, "課程工作區格式錯誤：confirmed 應為字串陣列。"
    if not isinstance(week_one_mondays, dict):
        return {}, "課程工作區格式錯誤：week_one_mondays 應為 JSON 物件。"
    for semester, monday_text in week_one_mondays.items():
        if not isinstance(semester, str) or not isinstance(monday_text, str):
            return {}, "課程工作區格式錯誤：學期週次日期應為文字。"
        try:
            monday = date.fromisoformat(monday_text)
        except ValueError:
            return {}, "課程工作區格式錯誤：週次日期應使用 YYYY-MM-DD。"
        if monday.weekday() != 0:
            return {}, "課程工作區格式錯誤：第 1 週日期必須是星期一。"
    if not isinstance(notes, dict):
        return {}, "課程工作區格式錯誤：notes 應為 JSON 物件。"
    for key, note in notes.items():
        if not isinstance(key, str) or not isinstance(note, dict):
            return {}, "課程工作區格式錯誤：筆記項目應為 JSON 物件。"
        if not isinstance(note.get("text", ""), str):
            return {}, "課程工作區格式錯誤：筆記文字應為字串。"
        attachments = note.get("attachments", [])
        if not isinstance(attachments, list) or not all(
            isinstance(attachment, dict)
            and isinstance(attachment.get("file"), str)
            and isinstance(attachment.get("name"), str)
            and isinstance(attachment.get("mime_type"), str)
            for attachment in attachments
        ):
            return {}, "課程工作區格式錯誤：附件清單格式不正確。"
    return {
        "confirmed": confirmed,
        "notes": notes,
        "week_one_mondays": week_one_mondays,
    }, ""


def save_course_workspace(workspace, file_path):
    """以暫存檔取代工作區 JSON，避免寫入中斷造成檔案不完整。"""
    temporary_path = str(file_path) + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(workspace, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, file_path)
        return ""
    except OSError as error:
        return "儲存課程工作區失敗：" + str(error)


def save_media_upload(content, original_name, mime_type, media_directory, existing):
    """儲存一張圖片或一段錄音；附件使用隨機檔名，避免路徑注入。"""
    if not isinstance(content, bytes) or not content:
        return None, False, "附件是空的，沒有儲存。"
    mime_type = str(mime_type or "").lower()
    extension = MEDIA_EXTENSIONS.get(mime_type)
    if not extension:
        return None, False, "不支援此附件格式：" + mime_type
    limit = MAX_IMAGE_BYTES if mime_type.startswith("image/") else MAX_AUDIO_BYTES
    if len(content) > limit:
        limit_mb = limit // (1024 * 1024)
        return None, False, "附件超過 " + str(limit_mb) + " MB，沒有儲存。"

    content_hash = hashlib.sha256(content).hexdigest()
    for attachment in existing:
        if attachment.get("sha256") == content_hash:
            return None, True, ""

    filename = uuid.uuid4().hex + extension
    path = Path(media_directory) / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except OSError as error:
        return None, False, "儲存附件失敗：" + str(error)

    safe_name = str(original_name or "附件").replace("\\", "/").rsplit("/", 1)[-1]
    return {
        "file": filename,
        "name": safe_name[:200],
        "mime_type": mime_type,
        "sha256": content_hash,
    }, False, ""
