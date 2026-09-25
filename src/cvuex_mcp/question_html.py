"""Reading the questions of a quiz review, which Moodle sends already rendered as HTML.

The layout comes from Moodle's question renderer (question/engine/renderer.php):

    .que
      .info                     number, state and mark (sent apart as fields)
      .content
        .formulation  .qtext    the statement
                      .ablock   the answer, with the student's choices and inputs
        .outcome      .specificfeedback .generalfeedback .rightanswer
        .comment                the teacher's comment
        .history                every step of the attempt (left out)

Moodle only renders what the teacher lets the student review.
"""

from dataclasses import dataclass
from html.parser import HTMLParser

from cvuex_mcp.formatting import tidy_text

# Class of the element that starts each part, and the part it goes to.
PART_CLASSES = {
    "qtext": "statement",
    "ablock": "answer",
    "specificfeedback": "feedback",
    "numpartscorrect": "feedback",
    "generalfeedback": "feedback",
    "rightanswer": "right_answer",
    "comment": "comment",
}
# Elements whose text is left out: headings for screen readers, the history...
SKIPPED_CLASSES = {"info", "history", "accesshide", "visually-hidden", "sr-only", "questionflag"}
SKIPPED_TAGS = {"script", "style"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "wbr"}
LINE_BREAK_TAGS = {"br", "p", "div", "li", "tr", "fieldset", "legend", "h3", "h4", "h5"}
# In the answer, choices are laid out with nested divs: one line per choice row only.
CHOICE_ROW_CLASSES = {"r0", "r1"}


@dataclass
class QuestionParts:
    statement: str = ""
    answer: str = ""
    """What the student answered: ``[x]``/``[ ]`` for choices, ``[text]`` for inputs."""
    feedback: str = ""
    right_answer: str = ""
    comment: str = ""


def question_parts(html: str) -> QuestionParts:
    parser = _QuestionParser()
    parser.feed(html)
    parser.close()
    return QuestionParts(**{part: tidy_text("".join(text)) for part, text in parser.parts.items()})


@dataclass
class _Element:
    tag: str
    part: str | None
    skipped: bool
    separator: str
    """What goes before and after its text: a line break, a space or nothing."""


class _QuestionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open: list[_Element] = []
        self.parts: dict[str, list[str]] = {part: [] for part in PART_CLASSES.values()}
        self.in_select = False
        self.in_selected_option = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        parent = self.open[-1] if self.open else _Element("", None, False, "")
        part = parent.part or next((PART_CLASSES[c] for c in classes if c in PART_CLASSES), None)
        skipped = parent.skipped or tag in SKIPPED_TAGS or bool(classes & SKIPPED_CLASSES)
        separator = _separator(tag, classes, part)
        if tag not in VOID_TAGS:
            self.open.append(_Element(tag, part, skipped, separator))
        if part is None or skipped:
            return

        self._write(part, separator)
        if tag == "input":
            self._write(part, _input_text(attributes))
        elif tag == "img":
            alt = attributes.get("alt")
            self._write(part, f"[imagen: {alt}]" if alt else "[imagen]")
        elif "icon" in classes and attributes.get("title"):
            self._write(part, f" ({attributes['title']}) ")  # e.g. the "correct" mark
        elif tag == "select":
            self.in_select = True
        elif tag == "option" and "selected" in attributes:
            self.in_selected_option = True
            self._write(part, "[")

    def handle_endtag(self, tag: str) -> None:
        # Close up to the matching element, tolerating unclosed ones.
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index].tag == tag:
                element = self.open[index]
                del self.open[index:]
                break
        else:
            return
        if element.part is None or element.skipped:
            return
        if tag == "option" and self.in_selected_option:
            self.in_selected_option = False
            self._write(element.part, "] ")
        elif tag == "select":
            self.in_select = False
        else:
            self._write(element.part, element.separator)

    def handle_data(self, data: str) -> None:
        element = self.open[-1] if self.open else None
        if element is None or element.part is None or element.skipped:
            return
        if self.in_select and not self.in_selected_option:
            return  # only the chosen option of a drop-down
        self._write(element.part, data)

    def _write(self, part: str, text: str) -> None:
        self.parts[part].append(text)


def _input_text(attributes: dict[str, str | None]) -> str:
    kind = attributes.get("type", "text")
    if kind in ("radio", "checkbox"):
        return "[x] " if "checked" in attributes else "[ ] "
    if kind in ("hidden", "submit", "button"):
        return ""
    return f"[{attributes.get('value') or ''}]"


def _separator(tag: str, classes: set[str], part: str | None) -> str:
    if tag not in LINE_BREAK_TAGS:
        return ""
    if tag == "div" and part == "answer" and not classes & CHOICE_ROW_CLASSES:
        return " "
    return "\n"
