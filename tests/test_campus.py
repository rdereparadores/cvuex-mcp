import pytest
from helpers import FakeMoodle, load_fixture

from cvuex_mcp.campus import ALLOWED_FUNCTIONS, Campus, FunctionNotAllowedError

SITE_INFO = "core_webservice_get_site_info"


@pytest.fixture
def fake_moodle() -> FakeMoodle:
    return FakeMoodle({SITE_INFO: load_fixture(SITE_INFO)})


async def test_site_info(fake_moodle):
    info = await Campus(fake_moodle.client()).site_info()
    assert info.full_name == "Persona 4"
    assert info.user_id == 1001
    assert info.site_name == "Aulas regladas (AVUEx)"


async def test_user_id_reuses_cached_site_info(fake_moodle):
    campus = Campus(fake_moodle.client())
    await campus.site_info()
    assert await campus.user_id() == 1001
    assert fake_moodle.functions_called() == [SITE_INFO]


async def test_functions_outside_the_allowlist_are_never_sent(fake_moodle):
    campus = Campus(fake_moodle.client())
    with pytest.raises(FunctionNotAllowedError):
        await campus._call("mod_assign_save_submission", assignmentid=1)
    assert fake_moodle.calls == []


def test_allowlist_has_only_read_functions():
    for function in ALLOWED_FUNCTIONS:
        assert "_get_" in function, function
        assert "_view_" not in function, function


COURSES = "core_course_get_enrolled_courses_by_timeline_classification"


async def test_courses():
    fake = FakeMoodle({COURSES: load_fixture(COURSES)})
    courses = await Campus(fake.client()).courses("inprogress")

    assert [course.id for course in courses] == [32338, 32337, 32327]
    first = courses[0]
    assert first.nombre == "APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO"
    assert first.titulacion == "Máster Universitario en Ingeniería Informática"
    assert first.url == "https://campusvirtual.unex.es/zonauex/avuex/course/view.php?id=32338"
    assert fake.calls[0]["classification"] == "inprogress"


async def test_course_progress_only_when_moodle_tracks_it():
    answer = load_fixture(COURSES)
    untracked, tracked, *_ = answer["courses"]
    untracked |= {"hasprogress": False, "progress": 0}
    tracked |= {"hasprogress": True, "progress": 66.6667}

    courses = await Campus(FakeMoodle({COURSES: answer}).client()).courses("all")
    assert [course.progreso for course in courses[:2]] == [None, 67]
