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
}
