"""The Moodle web service functions the server may call.

The student's token can do much more (submit work, post in forums...), so this
table is the safety net: add a function only when a tool needs it, after
checking in Moodle's source that it has no side effects. Never add *_view_*
functions: they log accesses and can mark activities as completed.

Each function maps to how long its answers are cached, in seconds (0 = never).
"""

ALLOWED_FUNCTIONS: dict[str, float] = {
    # Account and courses
    "core_webservice_get_site_info": 3600,
    "core_course_get_enrolled_courses_by_timeline_classification": 600,
    # Deadlines
    "core_calendar_get_action_events_by_timesort": 120,
    "core_calendar_get_action_events_by_course": 120,
    "core_calendar_get_calendar_events": 120,
    # Assignments
    "mod_assign_get_assignments": 300,
    "mod_assign_get_submission_status": 120,
    # Changes
    "core_course_get_updates_since": 0,
    "core_course_get_contents": 600,
    # Notifications
    "message_popup_get_popup_notifications": 60,
    # Forums. get_discussion_posts marks the posts as read if the student tracks the forum.
    "mod_forum_get_forums_by_courses": 600,
    "mod_forum_get_forum_discussions": 120,
    "mod_forum_get_discussion_posts": 60,
    # Grades. core_grades_get_gradeitems only gives the category of each item.
    "gradereport_overview_get_course_grades": 300,
    "gradereport_user_get_grade_items": 120,
    "core_grades_get_gradeitems": 600,
    # Quizzes: only finished attempts, and only what Moodle lets the student review.
    # Never mod_quiz_get_attempt_data, start_attempt, process_attempt or save_attempt.
    "mod_quiz_get_quizzes_by_courses": 600,
    "mod_quiz_get_user_quiz_attempts": 120,
    "mod_quiz_get_attempt_review": 300,
}
