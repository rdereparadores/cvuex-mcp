import pytest
from helpers import COURSES, FakeMoodle, load_fixture

from cvuex_mcp.campus import Campus
from cvuex_mcp.forum_search import refresh as refresh_module
from cvuex_mcp.forum_search.index import Discussion, ForumIndex, Post
from cvuex_mcp.forum_search.refresh import ForumProgress, is_stale, refresh_forums
from cvuex_mcp.forum_search.search import search_forums
from cvuex_mcp.models import Asignatura
from cvuex_mcp.moodle import InvalidTokenError

FORUMS = "mod_forum_get_forums_by_courses"
DISCUSSIONS = "mod_forum_get_forum_discussions"
POSTS = "mod_forum_get_discussion_posts"
NO_DISCUSSIONS = {"discussions": [], "warnings": []}
COURSE = Asignatura(
    id=32338,
    nombre="APRENDIZAJE AUTOMÁTICO Y APRENDIZAJE PROFUNDO",
    titulacion="",
    progreso=None,
    url="",
)
URL = "https://campusvirtual.unex.es/zonauex/avuex/mod/forum/discuss.php?d="


def answered_discussion() -> dict:
    """The real announcement, now with a reply (its posts come from the real fixture)."""
    discussion = load_fixture(DISCUSSIONS)["discussions"][0]
    return dict(discussion, discussion=41900, name="Dudas de la práctica", numreplies=1)


class Setup:
    """The real forums of course 32338: one announcement, and one discussion with a reply."""

    def __init__(self, tmp_path) -> None:
        self.discussions = [load_fixture(DISCUSSIONS)["discussions"][0], answered_discussion()]
        posts = load_fixture(POSTS)
        reply = dict(
            posts["posts"][0],
            id=64300,
            subject="Re: Dudas de la práctica",
            message="<p>La práctica se entrega en formato ZIP.</p>",
            author={"fullname": "Persona 3"},
            timecreated=1790200000,
        )
        posts["posts"].append(reply)
        self.fake = FakeMoodle(
            {
                COURSES: load_fixture(COURSES),
                FORUMS: [load_fixture(FORUMS)[0]],  # 72401, the course's only forum
                DISCUSSIONS: self._discussions,
                POSTS: posts,
            }
        )
        self.campus = Campus(self.fake.client())
        self.path = tmp_path / "foros.sqlite"

    def _discussions(self, form: dict) -> dict:
        page, per_page = int(form["page"]), int(form["perpage"])
        return {"discussions": self.discussions[page * per_page : (page + 1) * per_page]}

    async def refresh(self) -> ForumProgress:
        progress = ForumProgress()
        await refresh_forums(self.campus, [COURSE], progress, index_path=self.path)
        return progress

    def index(self) -> ForumIndex:
        return ForumIndex(self.path)

    def posts_calls(self) -> list[str]:
        return [call["discussionid"] for call in self.fake.calls if call["wsfunction"] == POSTS]


@pytest.fixture
def setup(tmp_path) -> Setup:
    return Setup(tmp_path)


async def test_refresh_indexes_every_post(setup):
    progress = await setup.refresh()
    assert (progress.discussions, progress.checked, progress.updated) == (2, 2, 2)
    # Only the discussion with replies needs its posts; the other came in the list.
    assert setup.posts_calls() == ["41900"]

    index = setup.index()
    matches, all_words = index.search("formato zip")
    [match] = matches
    assert all_words
    assert (match.discussion.title, match.author) == ("Dudas de la práctica", "Persona 3")
    assert match.snippet == "La práctica se entrega en «formato» «ZIP»."
    assert index.count() == 2


async def test_second_refresh_only_reads_what_changed(setup):
    await setup.refresh()
    setup.fake.calls.clear()
    setup.discussions[1] = dict(setup.discussions[1], timemodified=1790300000)  # a new reply

    progress = await setup.refresh()
    assert progress.updated == 1
    assert setup.posts_calls() == ["41900"]


async def test_discussions_deleted_in_the_campus_are_forgotten(setup):
    await setup.refresh()
    setup.discussions.pop()
    progress = await setup.refresh()
    assert progress.removed == 1
    assert setup.index().search("zip")[0] == []


async def test_a_forum_that_fails_keeps_its_discussions(setup):
    await setup.refresh()
    setup.fake.answers[DISCUSSIONS] = {
        "exception": "x",
        "errorcode": "nopermissions",
        "message": "No",
    }
    progress = await setup.refresh()
    assert progress.removed == 0
    assert progress.warnings == ["No se pudo consultar el foro Foro general de la asignatura: No"]
    assert setup.index().count() == 2


async def test_discussions_come_page_by_page(setup, monkeypatch):
    monkeypatch.setattr(refresh_module, "PER_PAGE", 1)
    progress = await setup.refresh()
    pages = [call["page"] for call in setup.fake.calls if call["wsfunction"] == DISCUSSIONS]
    assert (pages, progress.discussions) == (["0", "1", "2"], 2)


async def test_an_expired_session_stops_the_refresh(setup):
    setup.fake.answers[POSTS] = {"exception": "x", "errorcode": "invalidtoken", "message": "No"}
    with pytest.raises(InvalidTokenError):
        await setup.refresh()


async def test_refreshed_courses_stay_fresh_for_a_while(setup):
    await setup.refresh()
    index = setup.index()
    refreshed = index.refreshed_at(COURSE.id)
    assert not is_stale(index, COURSE.id, refreshed + 60)
    assert is_stale(index, COURSE.id, refreshed + refresh_module.FRESH_FOR_SECONDS + 1)
    assert is_stale(index, 99, refreshed)


def discussion(id: int, course_id: int = 32338, title: str = "Debate") -> Discussion:
    return Discussion(id, course_id, "Asignatura", "Foro", title, 2, 1790000000, f"{URL}{id}")


def test_one_result_per_discussion_with_its_best_post(tmp_path):
    index = ForumIndex(tmp_path / "foros.sqlite")
    index.store(
        discussion(1, title="Examen"),
        [
            Post("Examen", "¿Cuándo es el examen?", "Persona 1", 1790000000),
            Post(
                "Re: Examen", "El examen de junio es el día 10; el examen de julio, el 3.", None, 0
            ),
        ],
    )
    index.store(discussion(2, course_id=1), [Post("Otro", "Nada que ver con exámenes", None, 0)])

    matches, _ = index.search("examen")
    assert [m.discussion.id for m in matches] == [1, 2]
    assert "«examen»" in matches[0].snippet  # from a message, not the repeated title
    assert [m.discussion.id for m in index.search("EXAMENES", course_id=1)[0]] == [2]


def test_results_say_when_the_index_is_still_updating(tmp_path):
    index = ForumIndex(tmp_path / "foros.sqlite")
    progress = ForumProgress(discussions=40, checked=12)
    result = search_forums(index, "examen", None, 10, progress=progress, refreshing=True)
    assert not result.indice_al_dia
    assert result.avisos == [
        "Actualizando el índice de los foros: 12 de 40 debates revisados por ahora."
    ]
