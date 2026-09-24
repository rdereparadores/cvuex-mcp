"""Read-only access to the student's campus: the only way tools talk to Moodle.

``core`` has what every area needs (:class:`Campus`). Each other module is an
area (deadlines, assignments...) with functions that take a ``Campus``.
"""

from cvuex_mcp.campus.core import Campus, CourseClassification, FunctionNotAllowedError, SiteInfo

__all__ = ["Campus", "CourseClassification", "FunctionNotAllowedError", "SiteInfo"]
