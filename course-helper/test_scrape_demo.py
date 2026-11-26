import unittest

import app
import scrape_demo


class ScrapeDemoTests(unittest.TestCase):
    def test_extracts_course_fields_and_original_periods(self):
        page = """
        <table>
          <tr class="odd">
            <td>07001<br />CC0109-*</td>
            <td>Art of Asia
              <span class="engclass">亞洲藝術</span>
              <span class="descript">[Code Card:Optional][Not for preliminary]</span>
            </td>
            <td>I-JAN,LEE</td>
            <td>2</td>
            <td><span class="classtime">Wed34/TR-A203<br /></span></td>
            <td>Elective</td>
          </tr>
        </table>
        """

        courses = scrape_demo.parse_courses(
            page,
            "1151",
            "核心通識課程",
            "https://cis.ncu.edu.tw/Course/main/query/byKeywords?semester=1151",
        )

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_id"], "CC0109-*")
        self.assertEqual(courses[0]["course_name"], "亞洲藝術")
        self.assertEqual(courses[0]["teacher"], "I-JAN,LEE")
        self.assertEqual(courses[0]["credits"], 2)
        self.assertFalse(courses[0]["is_required"])
        self.assertEqual(courses[0]["offering_type"], "選修")
        self.assertEqual(courses[0]["code_card_requirement"], "可選")
        self.assertTrue(courses[0]["not_for_preliminary"])
        self.assertEqual(courses[0]["teacher_gmail"], "未提供")
        self.assertEqual(courses[0]["time"], "Wed34/TR-A203")
        self.assertEqual(
            courses[0]["meeting_times"],
            [{
                "day": "三",
                "periods": "34",
                "start": "10:00",
                "end": "11:50",
            }],
        )

    def test_converts_periods_using_ncu_clock_times(self):
        self.assertEqual(
            scrape_demo.parse_meeting_days("Mon1 Tue5 WedA"),
            [
                {"day": "一", "periods": "1", "start": "08:00", "end": "08:50"},
                {"day": "二", "periods": "5", "start": "13:00", "end": "13:50"},
                {"day": "三", "periods": "A", "start": "18:00", "end": "18:50"},
            ],
        )
        self.assertEqual(
            scrape_demo.parse_meeting_days("Mon45"),
            [
                {"day": "一", "periods": "4", "start": "11:00", "end": "11:50"},
                {"day": "一", "periods": "5", "start": "13:00", "end": "13:50"},
            ],
        )
        self.assertEqual(
            scrape_demo.parse_meeting_days("Mon4Z"),
            [{"day": "一", "periods": "4Z"}],
        )

    def test_extracts_required_status(self):
        page = """
        <table>
          <tr>
            <td>07002<br />CS1001-A</td>
            <td>Programming</td>
            <td>Teacher</td>
            <td>3</td>
            <td><span class="classtime">Tue12</span></td>
            <td>Required</td>
          </tr>
        </table>
        """

        courses = scrape_demo.parse_courses(
            page,
            "1151",
            "Computer Science",
            "https://cis.ncu.edu.tw/Course/main/query",
        )

        self.assertEqual(courses[0]["is_required"], True)
        self.assertEqual(courses[0]["offering_type"], "必修")

    def test_formats_password_card_and_preliminary_restrictions(self):
        self.assertEqual(
            scrape_demo.parse_course_restrictions(
                "[Code Card:Required][Not for preliminary]"
            ),
            ("需要", True),
        )
        self.assertEqual(
            scrape_demo.parse_course_restrictions("[Code Card:Optional]"),
            ("可選", None),
        )
        self.assertEqual(
            app.format_course_restrictions({
                "code_card_requirement": "需要",
                "not_for_preliminary": True,
            }),
            "需要密碼卡；不列入初選分發",
        )
        self.assertEqual(
            app.valid_teacher_gmail("teacher.name@gmail.com"),
            "teacher.name@gmail.com",
        )
        self.assertEqual(app.valid_teacher_gmail("teacher@dept.ncu.edu.tw"), "")

    def test_extracts_selected_term(self):
        page = "<select><option selected value='1151'>2026 Fall</option></select>"
        self.assertEqual(scrape_demo.get_term(page), "1151")

    def test_finds_the_general_education_department(self):
        departments = [
            {"deptName": ["核心通識課程", "Core and Generals Education Courses"], "key": "1151:0-0099-0"},
        ]
        department = scrape_demo.find_department(departments, "通識")
        self.assertEqual(department["key"], "1151:0-0099-0")

    def test_keeps_different_semesters_separate(self):
        courses = [
            {"semester": "1151", "course_id": "GE1001"},
            {"semester": "1152", "course_id": "EE5001"},
        ]
        result = app.courses_for_semester(courses, "1151")
        self.assertEqual([course["course_id"] for course in result], ["GE1001"])

    def test_department_list_includes_english_and_excludes_core_general_education(self):
        courses = [
            {"department": "中國文學系"},
            {"department": "英美語文學系"},
            {"department": "核心通識課程"},
            {"department": "通識教育中心"},
            {"department": "數學系"},
        ]

        departments = app.departments_for_selection(courses)

        self.assertEqual(departments, ["中國文學系", "英美語文學系", "數學系"])

    def test_general_education_has_separate_type_and_category_filters(self):
        courses = [
            {"course_id": "CORE1", "department": "核心通識課程"},
            {"course_id": "GS1", "department": "通識教育中心"},
            {"course_id": "CS1", "department": "資訊工程學系"},
        ]

        general_courses = app.filter_course_scope(
            courses,
            "通識課程",
            "",
            {"GS1": "藝術"},
        )
        art_courses = app.filter_course_scope(
            courses,
            "通識課程",
            "藝術",
            {"GS1": "藝術"},
        )

        self.assertEqual(
            [course["course_id"] for course in general_courses],
            ["CORE1", "GS1"],
        )
        self.assertEqual([course["course_id"] for course in art_courses], ["GS1"])
        self.assertEqual(app.course_type_label(courses[0]), "核心通識")
        self.assertEqual(app.course_type_label(courses[1]), "一般通識")

    def test_schedule_course_filter_allows_blank_class_and_unlimited_courses(self):
        courses = [
            {
                "course_id": "CS201-A",
                "department": "資工系",
                "target_year": "大二",
                "section": "甲",
            },
            {
                "course_id": "CS201-B",
                "department": "資工系",
                "target_year": "大二",
                "section": "乙",
            },
            {
                "course_id": "GE101-*",
                "department": "資工系",
                "target_year": "不限",
                "section": "*",
            },
            {
                "course_id": "GE102-*",
                "department": "資工系",
                "target_year": "未提供",
                "section": "*",
            },
            {
                "course_id": "EE201-A",
                "department": "電機系",
                "target_year": "大二",
                "section": "甲",
            },
        ]

        all_classes = app.filter_schedule_courses(courses, "資工系", "大二", "")
        one_class = app.filter_schedule_courses(courses, "資工系", "大二", "甲")

        self.assertEqual(
            [course["course_id"] for course in all_classes],
            ["CS201-A", "CS201-B", "GE101-*", "GE102-*"],
        )
        self.assertEqual(
            [course["course_id"] for course in one_class],
            ["CS201-A", "GE101-*", "GE102-*"],
        )

    def test_compare_shows_official_category_or_uncategorized_label(self):
        courses = [
            {
                "offering_id": "A",
                "course_id": "GE1",
                "department": "通識教育中心",
                "teacher_gmail": "teacher@gmail.com",
                "sources": [{
                    "url": "https://example.edu/profile",
                    "fields": ["teacher_gmail"],
                }],
            },
            {
                "offering_id": "B",
                "course_id": "GE2",
                "department": "核心通識課程",
            },
        ]

        compared = app.compare_courses(
            courses,
            ["A", "B"],
            {"GE1": "人文藝術"},
        )

        self.assertEqual(compared[0]["general_education_category"], "人文藝術")
        self.assertEqual(compared[1]["general_education_category"], "未分類")
        self.assertEqual(compared[0]["teacher_gmail"], "teacher@gmail.com")
        self.assertEqual(compared[1]["teacher_gmail"], "")

    def test_default_scrape_does_not_include_1152(self):
        self.assertEqual(len(scrape_demo.DEFAULT_DEMO_QUERIES), 11)
        self.assertEqual(
            {semester for semester, department in scrape_demo.DEFAULT_DEMO_QUERIES},
            {"1151"},
        )
        self.assertEqual(
            {department for semester, department in scrape_demo.DEFAULT_DEMO_QUERIES},
            set(scrape_demo.DEFAULT_DEPARTMENTS + scrape_demo.GENERAL_EDUCATION_UNITS),
        )

    def test_week_calendar_uses_one_hour_rows(self):
        slots = app.hourly_time_slots()

        self.assertEqual(app.format_table_time(slots[0]), "08:00")
        self.assertEqual(app.format_table_time(slots[-1]), "22:00")
        self.assertTrue(all(
            later - earlier == 60
            for earlier, later in zip(slots, slots[1:])
        ))

    def test_recommendations_create_distinct_interest_based_options(self):
        courses = [
            {
                "offering_id": "1151-1",
                "course_id": "GE1",
                "course_name": "亞洲藝術",
                "credits": 2,
            },
            {
                "offering_id": "1151-2",
                "course_id": "GE2",
                "course_name": "自然科學導論",
                "credits": 2,
            },
        ]

        schedules, missing = app.recommend_schedules(
            courses,
            None,
            ["藝術"],
            2,
            2,
            2,
            [],
            {},
        )

        self.assertEqual(missing, [])
        self.assertEqual(len(schedules), 2)
        self.assertEqual(schedules[0]["courses"][0]["course_id"], "GE1")
        self.assertEqual(schedules[1]["courses"][0]["course_id"], "GE2")

    def test_recommendations_prioritize_courses_on_preferred_days(self):
        courses = [
            {
                "offering_id": "1151-1",
                "course_id": "GE1",
                "course_name": "課程一",
                "credits": 2,
                "meeting_times": [{"day": "一"}],
            },
            {
                "offering_id": "1151-2",
                "course_id": "GE2",
                "course_name": "課程二",
                "credits": 2,
                "meeting_times": [{"day": "三"}],
            },
        ]

        schedules, missing = app.recommend_schedules(
            courses,
            None,
            [],
            2,
            2,
            1,
            [],
            {},
            ["三"],
        )

        self.assertEqual(missing, [])
        self.assertEqual(schedules[0]["courses"][0]["course_id"], "GE2")

    def test_recommendations_prioritize_courses_overlapping_preferred_time_slots(self):
        courses = [
            {
                "offering_id": "1151-1",
                "course_id": "GE1",
                "course_name": "課程一",
                "credits": 2,
                "meeting_times": [{
                    "day": "三",
                    "start": "10:00",
                    "end": "10:50",
                }],
            },
            {
                "offering_id": "1151-2",
                "course_id": "GE2",
                "course_name": "課程二",
                "credits": 2,
                "meeting_times": [{
                    "day": "三",
                    "start": "09:00",
                    "end": "09:50",
                }],
            },
        ]

        schedules, missing = app.recommend_schedules(
            courses,
            None,
            [],
            2,
            2,
            1,
            [],
            {},
            [],
            ["三|540"],
        )

        self.assertEqual(missing, [])
        self.assertEqual(schedules[0]["courses"][0]["course_id"], "GE2")

    def test_recommendations_without_curriculum_stay_within_selected_department(self):
        courses = [
            {"course_id": "CH1", "department": "中國文學系"},
            {"course_id": "CORE1", "department": "核心通識課程"},
            {"course_id": "GS1", "department": "通識教育中心"},
            {"course_id": "MA1", "department": "數學系"},
        ]

        selected_department_courses = app.courses_for_recommendation(
            courses,
            "中國文學系",
            None,
        )
        all_courses = app.courses_for_recommendation(courses, "", None)

        self.assertEqual(
            [course["course_id"] for course in selected_department_courses],
            ["CH1", "CORE1", "GS1"],
        )
        self.assertEqual(len(all_courses), 4)

    def test_recommendations_include_verified_requirements_and_report_missing_ids(self):
        courses = [
            {
                "offering_id": "1151-1",
                "course_id": "CS1001",
                "course_name": "程式設計",
                "credits": 3,
            },
            {
                "offering_id": "1151-2",
                "course_id": "GE1",
                "course_name": "通識課程",
                "credits": 2,
            },
        ]
        curriculum = {
            "required_course_ids": ["CS1001", "CS9999"],
            "elective_course_ids": [],
        }

        schedules, missing = app.recommend_schedules(
            courses,
            curriculum,
            [],
            6,
            6,
            2,
            [],
            {},
        )

        self.assertEqual(missing, ["CS9999"])
        self.assertIn("CS1001", [
            course["course_id"] for course in schedules[0]["courses"]
        ])


if __name__ == "__main__":
    unittest.main()
