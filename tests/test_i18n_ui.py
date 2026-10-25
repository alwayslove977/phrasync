from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "i18n_ui.cjs"


def run_group(group: str) -> None:
    """Run one group of tests/i18n_ui.cjs, which evaluates the real scripts."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    result = subprocess.run(
        [node, str(HARNESS), group],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_engine_and_dom_expose_different_halves():
    """i18n.js owns window.t/tm; i18n-dom.js owns initI18n and the controls."""
    run_group("exports")


def test_language_switches_round_trip_and_persist():
    """State, <html lang> and storage move together, and only the engine writes."""
    run_group("language")


def test_attribute_and_english_source_state_machines_survive_the_split():
    """P1-1 (source + rendered) and P1-2 (English-mode source) still hold."""
    run_group("dom-state")


def test_observer_registration_is_idempotent():
    run_group("observer")


def test_current_language_has_one_declaration_and_one_writer():
    run_group("structure")


def test_assembled_sentences_round_trip_between_languages():
    """A sentence built from several t() fragments must come back in English."""
    run_group("assembled")


def test_assembled_sentences_switch_from_english_without_a_refetch():
    """Rendered in English first, the pair must already exist: no health retry."""
    run_group("bidirectional")


def test_translation_order_is_dictionary_pattern_then_registered():
    """Dictionary, then pattern rules, then registered assembled text, then raw."""
    run_group("priority")
