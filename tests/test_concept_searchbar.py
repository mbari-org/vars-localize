from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

CONCEPTS = ["Beroe", "Bathochordaeus", "Bathochordaeus mcnutti", "Bathybembix", "fish"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(qapp):
    from vars_localize.ui.ConceptSearchbar import ConceptSearchbar

    widget = ConceptSearchbar()
    widget.set_concepts(CONCEPTS)
    return widget


def _type(widget, text):
    for ch in text:
        widget.keyPressEvent(
            QKeyEvent(QKeyEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch)
        )


def _key(widget, key):
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    )


def test_find_concept_is_case_insensitive(bar):
    assert bar.find_concept(" beroe ") == "Beroe"
    assert bar.find_concept("FISH") == "fish"
    assert bar.find_concept("bero") == ""


def test_first_prefix_match_prefers_shortest(bar):
    assert bar.first_prefix_match("bathoch") == "Bathochordaeus"
    assert bar.first_prefix_match("bathy") == "Bathybembix"
    assert bar.first_prefix_match("zzz") == ""
    assert bar.first_prefix_match("") == ""


def test_typing_fills_and_recases_with_suffix_selected(bar):
    _type(bar, "bero")
    assert bar.text() == "Beroe"
    assert bar.selectedText() == "e"


def test_full_lowercase_word_is_recased(bar):
    _type(bar, "beroe")
    assert bar.text() == "Beroe"
    assert not bar.hasSelectedText()


def test_continued_typing_replaces_completion(bar):
    _type(bar, "bath")
    assert bar.text() == "Bathochordaeus"
    _type(bar, "y")
    assert bar.text() == "Bathybembix"
    assert bar.selectedText() == "bembix"


def test_backspace_removes_completion_without_refilling(bar):
    _type(bar, "bero")
    _key(bar, Qt.Key.Key_Backspace)
    assert bar.text() == "Bero"
    assert not bar.hasSelectedText()


def test_no_match_leaves_text_alone(bar):
    _type(bar, "xyz")
    assert bar.text() == "xyz"
