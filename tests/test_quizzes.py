import pytest
from helpers import COURSES, NOW, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.campus import quizzes as quizzes_module
from cvuex_mcp.campus.quizzes import QuizReviewError, quizzes, review_attempt
from cvuex_mcp.moodle import InvalidTokenError
from cvuex_mcp.question_html import question_parts

QUIZZES = "mod_quiz_get_quizzes_by_courses"
ATTEMPTS = "mod_quiz_get_user_quiz_attempts"
REVIEW = "mod_quiz_get_attempt_review"
NO_ATTEMPTS = {"attempts": [], "warnings": []}
URL = "https://campusvirtual.unex.es/zonauex/avuex"


def campus_with_quizzes(quizzes_answer=None) -> tuple[Campus, FakeMoodle]:
    """Synthetic data: only "Test tema 1" (7001) has finished attempts."""
    attempts = load_fixture(f"{ATTEMPTS}__sintetico")
    fake = FakeMoodle(
        {
            COURSES: load_fixture(COURSES),
            QUIZZES: quizzes_answer or load_fixture(f"{QUIZZES}__sintetico"),
            ATTEMPTS: lambda form: attempts if form["quizid"] == "7001" else NO_ATTEMPTS,
            REVIEW: load_fixture(f"{REVIEW}__sintetico"),
        }
    )
    return Campus(fake.client(), clock=lambda: NOW), fake


def moodle_error(errorcode: str) -> dict:
    return {"exception": "moodle_exception", "errorcode": errorcode, "message": "Error"}


async def test_quizzes():
    campus, fake = campus_with_quizzes()
    result = await quizzes(campus)

    # Most recent first; quizzes without dates last.
    assert [q.cuestionario for q in result.cuestionarios] == [
        "Test tema 3",
        "Test tema 2",
        "Test tema 1",
        "Autoevaluación",
    ]
    tema1 = result.cuestionarios[2]
    assert tema1.model_dump(exclude={"intentos"}) == {
        "cuestionario": "Test tema 1",
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "asignatura_id": 32338,
        "apertura": "2026-09-14T18:00+02:00",
        "cierre": "2026-09-21T18:00+02:00",
        "intentos_permitidos": 2,
        "nota_maxima": 10.0,
        "url": f"{URL}/mod/quiz/view.php?id=1840001",
    }
    assert [attempt.model_dump() for attempt in tema1.intentos] == [
        {
            "intento_id": 5001,
            "numero": 1,
            "fecha": "2026-09-19T18:00+02:00",
            "nota": 6.0,  # 3 marks out of 5, scaled to 10
            "retroalimentacion": "Aprobado. Repasa el tema 1.",
        },
        {
            "intento_id": 5002,
            "numero": 2,
            "fecha": "2026-09-20T18:00+02:00",
            "nota": 9.0,
            "retroalimentacion": "¡Muy bien!",
        },
    ]
    assert result.cuestionarios[3].intentos_permitidos is None  # unlimited
    assert result.avisos == []

    # Only finished attempts, and none asked for the quiz not open yet (7003).
    attempt_calls = [call for call in fake.calls if call["wsfunction"] == ATTEMPTS]
    assert [call["quizid"] for call in attempt_calls] == ["7002", "7001", "7004"]
    assert {call["status"] for call in attempt_calls} == {"finished"}
    forbidden = {"mod_quiz_get_attempt_data", "mod_quiz_start_attempt"}
    assert forbidden.isdisjoint(fake.functions_called())


async def test_quizzes_of_one_course():
    campus, fake = campus_with_quizzes()
    await quizzes(campus, course_id=32337)
    [call] = [call for call in fake.calls if call["wsfunction"] == QUIZZES]
    assert call["courseids[0]"] == "32337"
    assert "courseids[1]" not in call


async def test_hidden_grades_are_not_computed():
    """Moodle leaves the marks empty when the teacher doesn't show them."""
    campus, fake = campus_with_quizzes()
    attempts = load_fixture(f"{ATTEMPTS}__sintetico")
    attempts["attempts"][0]["sumgrades"] = None
    fake.answers[ATTEMPTS] = attempts
    result = await quizzes(campus)
    [tema1] = [q for q in result.cuestionarios if q.cuestionario == "Test tema 1"]
    assert [attempt.nota for attempt in tema1.intentos] == [None, 9.0]


async def test_quiz_that_cannot_be_read_is_reported():
    campus, fake = campus_with_quizzes()
    fake.answers[ATTEMPTS] = moodle_error("requireloginerror")
    result = await quizzes(campus)
    assert len(result.cuestionarios) == 1  # only the one not open, which needs no request
    assert len(result.avisos) == 3
    assert result.avisos[0].startswith("No se pudo consultar 'Test tema 2'")


async def test_expired_session_while_reading_attempts():
    campus, fake = campus_with_quizzes()
    fake.answers[ATTEMPTS] = moodle_error("invalidtoken")
    with pytest.raises(InvalidTokenError):
        await quizzes(campus)


async def test_too_many_quizzes(monkeypatch):
    monkeypatch.setattr(quizzes_module, "MAX_QUIZZES", 2)
    campus, _ = campus_with_quizzes()
    result = await quizzes(campus)
    assert [q.cuestionario for q in result.cuestionarios] == ["Test tema 3", "Test tema 2"]
    assert result.avisos[0].startswith("Hay 4 cuestionarios")


async def test_no_quizzes():
    """Real answer: no quizzes yet."""
    campus, fake = campus_with_quizzes(load_fixture(f"{QUIZZES}__vacio"))
    assert (await quizzes(campus)).cuestionarios == []
    assert ATTEMPTS not in fake.functions_called()


async def test_review():
    campus, fake = campus_with_quizzes()
    result = await review_attempt(campus, 5001)

    assert result.model_dump(exclude={"preguntas"}) == {
        "cuestionario": "Test tema 1",
        "asignatura": "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
        "intento_id": 5001,
        "intento_numero": 1,
        "fecha": "2026-09-19T18:00+02:00",
        "nota": 6.0,
        "nota_maxima": 10.0,
        "retroalimentacion_general": "Aprobado. Repasa el tema 1.",
        "url": f"{URL}/mod/quiz/review.php?attempt=5001",
    }
    multichoice, shortanswer, match, essay, description = result.preguntas
    assert multichoice.model_dump() == {
        "numero": "1",
        "tipo": "multichoice",
        "enunciado": "¿Qué orgánulo realiza la fotosíntesis?\n\n"
        "[imagen: Esquema de una célula vegetal]",
        "tu_respuesta": "Seleccione una:\n\n"
        "[x] a. El cloroplasto (Correcta) Exacto: contiene la clorofila.\n\n"
        "[ ] b. La mitocondria",
        "estado": "Correcta",
        "puntuacion": 1.0,
        "puntuacion_maxima": 1.0,
        "retroalimentacion": "La fotosíntesis ocurre en los cloroplastos.",
        "respuesta_correcta": "La respuesta correcta es: El cloroplasto",
        "comentario_profesor": None,
    }
    assert shortanswer.tu_respuesta == "Respuesta: [respiración] (Incorrecta)"
    assert shortanswer.retroalimentacion == "La respiración consume glucosa, no la produce."
    assert match.puntuacion == 0.5
    assert "[Energía] (Incorrecta)" in match.tu_respuesta
    assert "Elegir" not in match.tu_respuesta  # options not chosen are left out
    assert (essay.puntuacion, essay.puntuacion_maxima) == (1.5, 2.0)
    assert essay.comentario_profesor == "Falta mencionar la fotólisis del agua."
    assert (description.numero, description.estado, description.puntuacion) == ("i", None, None)

    [call] = [call for call in fake.calls if call["wsfunction"] == REVIEW]
    assert (call["attemptid"], call["page"]) == ("5001", "-1")


async def test_review_leaves_out_what_the_teacher_hides():
    campus, fake = campus_with_quizzes()
    review = load_fixture(f"{REVIEW}__sintetico")
    review["attempt"]["sumgrades"] = None
    review["additionaldata"] = []
    fake.answers[REVIEW] = review
    result = await review_attempt(campus, 5001)
    assert (result.nota, result.retroalimentacion_general) == (None, None)


@pytest.mark.parametrize(
    ("errorcode", "message"),
    [
        ("attemptclosed", "no está terminado"),
        ("noreview", "El profesor no permite revisar"),
        ("invalidrecord", "no existe o no es tuyo"),
    ],
)
async def test_reviews_moodle_refuses(errorcode, message):
    campus, fake = campus_with_quizzes()
    fake.answers[REVIEW] = moodle_error(errorcode)
    with pytest.raises(QuizReviewError, match=message):
        await review_attempt(campus, 5003)


async def test_expired_session_while_reviewing():
    campus, fake = campus_with_quizzes()
    fake.answers[REVIEW] = moodle_error("invalidtoken")
    with pytest.raises(InvalidTokenError):
        await review_attempt(campus, 5001)


def test_question_html_leaves_out_hidden_text_and_scripts():
    html = (
        '<div class="que"><div class="info">Pregunta 1</div>'
        '<div class="qtext">Enunciado<span class="accesshide"> oculto</span></div>'
        "<script>alert(1)</script>"
        '<div class="ablock"><input type="checkbox" checked="checked" /> Sí'
        '<input type="hidden" value="secreto" /></div>'
        '<div class="history">Paso 1</div></div>'
    )
    parts = question_parts(html)
    assert (parts.statement, parts.answer) == ("Enunciado", "[x] Sí")


async def test_marks_with_decimal_comma():
    """Seen on the campus: Moodle sends the marks formatted as in Spanish."""
    campus, fake = campus_with_quizzes()
    review = load_fixture(f"{REVIEW}__sintetico")
    review["questions"][2]["mark"] = "0,50"
    fake.answers[REVIEW] = review
    assert (await review_attempt(campus, 5001)).preguntas[2].puntuacion == 0.5


def test_choices_written_in_paragraphs_stay_on_one_line():
    """Seen on the campus: the text of each choice comes inside a paragraph."""
    html = (
        '<div class="ablock"><div class="answer">'
        '<div class="r0"><input type="radio" checked="checked" /><div class="d-flex">'
        '<span class="answernumber">a. </span><div class="flex-fill"><p>Primera<br></p></div>'
        "</div></div>"
        '<div class="r1"><input type="radio" /><div class="d-flex">'
        '<span class="answernumber">b. </span><div class="flex-fill"><p>Segunda</p></div>'
        "</div></div></div></div>"
    )
    assert question_parts(html).answer == "[x] a. Primera\n\n[ ] b. Segunda"
