"""The student's quizzes and the review of their finished attempts.

Academic integrity: only finished attempts, and only what Moodle already lets the
student review, following the teacher's review options. Attempts in progress are
never read.
"""

from typing import Any

from cvuex_mcp.campus.core import Campus
from cvuex_mcp.formatting import html_to_text, iso_datetime, module_url, quiz_review_url, truncate
from cvuex_mcp.models import (
    Cuestionario,
    IntentoCuestionario,
    ListaCuestionarios,
    PreguntaRevisada,
    RevisionCuestionario,
)
from cvuex_mcp.moodle import InvalidTokenError, MoodleError
from cvuex_mcp.question_html import question_parts

MAX_QUIZZES = 30  # each one needs its own request
MAX_TEXT_CHARS = 3000  # per part of a question


class QuizReviewError(Exception):
    """Moodle won't show the review; the message says why, for the student."""


# Why Moodle refuses a review, by error code.
REVIEW_ERRORS = {
    "attemptclosed": "El intento {id} no está terminado. Solo se pueden revisar intentos "
    "terminados: este servidor no ayuda con cuestionarios en curso.",
    "noreview": "El profesor no permite revisar el intento {id} ahora mismo. Según las opciones "
    "del cuestionario, puede permitirse más adelante (por ejemplo, cuando se cierre).",
}
UNKNOWN_ATTEMPT = (
    "No se pudo abrir el intento {id}: no existe o no es tuyo. "
    "Usa un intento_id de los que da cuestionarios."
)


async def quizzes(campus: Campus, course_id: int | None = None) -> ListaCuestionarios:
    """The student's quizzes with their finished attempts, most recent first.

    Without a course, it looks at the courses in progress. Each quiz needs its
    own request for the attempts, so at most ``MAX_QUIZZES`` are checked; quizzes
    not open yet can't have attempts and don't need one.
    """
    if course_id is not None:
        course_ids = [course_id]
    else:
        course_ids = [course.id for course in await campus.courses("inprogress")]
    if not course_ids:
        return ListaCuestionarios(cuestionarios=[], avisos=[])

    found = await _quizzes(campus, course_ids)
    found.sort(key=_latest_date, reverse=True)
    warnings = []
    if len(found) > MAX_QUIZZES:
        warnings.append(
            f"Hay {len(found)} cuestionarios; solo se han consultado los {MAX_QUIZZES} más "
            "recientes. Filtra por asignatura para ver el resto."
        )
        found = found[:MAX_QUIZZES]

    course_names = {course.id: course.nombre for course in await campus.courses("all")}
    now = campus.now()
    result = []
    for quiz in found:
        attempts = []
        if not quiz.get("timeopen") or quiz["timeopen"] <= now:
            try:
                answer = await campus.call(
                    "mod_quiz_get_user_quiz_attempts", quizid=quiz["id"], status="finished"
                )
            except InvalidTokenError:
                raise
            except MoodleError as error:
                warnings.append(f"No se pudo consultar '{quiz['name']}': {error}")
                continue
            attempts = answer["attempts"]
        result.append(_quiz(campus, quiz, attempts, course_names))
    return ListaCuestionarios(cuestionarios=result, avisos=warnings)


async def review_attempt(campus: Campus, attempt_id: int) -> RevisionCuestionario:
    """What the student can review of a finished attempt: grade, feedback and questions."""
    try:
        review = await campus.call("mod_quiz_get_attempt_review", attemptid=attempt_id, page=-1)
    except InvalidTokenError:
        raise
    except MoodleError as error:
        message = REVIEW_ERRORS.get(error.errorcode, UNKNOWN_ATTEMPT)
        raise QuizReviewError(message.format(id=attempt_id)) from error

    attempt = review["attempt"]
    # Any course: the attempt may belong to a past one.
    quiz = next((q for q in await _quizzes(campus, []) if q["id"] == attempt["quiz"]), {})
    course_names = {course.id: course.nombre for course in await campus.courses("all")}
    overall_feedback = next(
        (data["content"] for data in review["additionaldata"] if data["id"] == "feedback"), None
    )
    return RevisionCuestionario(
        cuestionario=quiz.get("name"),
        asignatura=course_names.get(quiz.get("course")),
        intento_id=attempt_id,
        intento_numero=attempt["attempt"],
        fecha=iso_datetime(attempt.get("timefinish")),
        nota=_grade(attempt.get("sumgrades"), quiz),
        nota_maxima=quiz.get("grade") or None,
        retroalimentacion_general=html_to_text(overall_feedback) or None,
        preguntas=[_question(question) for question in review["questions"]],
        url=quiz_review_url(campus.site, attempt_id),
    )


async def _quizzes(campus: Campus, course_ids: list[int]) -> list[dict[str, Any]]:
    """Quizzes of these courses; with no ids, of every course of the student."""
    answer = await campus.call("mod_quiz_get_quizzes_by_courses", courseids=course_ids)
    return list(answer["quizzes"])


def _latest_date(quiz: dict[str, Any]) -> int:
    return max(quiz.get("timeclose") or 0, quiz.get("timeopen") or 0)


def _quiz(
    campus: Campus,
    quiz: dict[str, Any],
    attempts: list[dict[str, Any]],
    course_names: dict[int, str],
) -> Cuestionario:
    return Cuestionario(
        cuestionario=quiz["name"],
        asignatura=course_names.get(quiz["course"]),
        asignatura_id=quiz["course"],
        apertura=iso_datetime(quiz.get("timeopen")),
        cierre=iso_datetime(quiz.get("timeclose")),
        intentos_permitidos=quiz.get("attempts") or None,  # 0 means unlimited
        nota_maxima=quiz.get("grade") or None,
        intentos=[_attempt(attempt, quiz) for attempt in attempts],
        url=module_url(campus.site, "quiz", quiz["coursemodule"]),
    )


def _attempt(attempt: dict[str, Any], quiz: dict[str, Any]) -> IntentoCuestionario:
    feedback = (attempt.get("feedback") or {}).get("feedbacktext")
    return IntentoCuestionario(
        intento_id=attempt["id"],
        numero=attempt["attempt"],
        fecha=iso_datetime(attempt.get("timefinish")),
        nota=_grade(attempt.get("sumgrades"), quiz),
        retroalimentacion=html_to_text(feedback) or None,
    )


def _grade(marks: float | None, quiz: dict[str, Any]) -> float | None:
    """Marks of an attempt → grade out of the quiz's maximum, as Moodle shows it.

    Moodle leaves the marks empty when the teacher doesn't let the student see them.
    """
    if marks is None or not quiz.get("sumgrades") or not quiz.get("grade"):
        return None
    return round(marks * quiz["grade"] / quiz["sumgrades"], quiz.get("decimalpoints", 2))


def _question(question: dict[str, Any]) -> PreguntaRevisada:
    parts = question_parts(question.get("html") or "")
    return PreguntaRevisada(
        numero=question.get("questionnumber") or None,
        tipo=question.get("type") or "",
        enunciado=truncate(parts.statement, MAX_TEXT_CHARS),
        tu_respuesta=truncate(parts.answer, MAX_TEXT_CHARS),
        estado=question.get("status"),
        puntuacion=_number(question.get("mark")),
        puntuacion_maxima=question.get("maxmark"),
        retroalimentacion=truncate(parts.feedback, MAX_TEXT_CHARS) or None,
        respuesta_correcta=truncate(parts.right_answer, MAX_TEXT_CHARS) or None,
        comentario_profesor=truncate(parts.comment, MAX_TEXT_CHARS) or None,
    )


def _number(value: str | float | None) -> float | None:
    """Question marks come as text in the campus's format, e.g. "0,50"."""
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None
