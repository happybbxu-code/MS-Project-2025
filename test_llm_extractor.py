import json

import pytest

from llm_extractor import (
    ExtractionError,
    extract_observations,
    fallback_extract_observations,
    parse_extraction,
)


def test_parse_extraction_accepts_fenced_valid_json():
    payload = {
        "observations": [
            {
                "fact": "cough",
                "status": "absent",
                "subject": "patient",
                "temporality": "current",
            },
            {
                "fact": "wheezing",
                "status": "present",
                "subject": "patient",
                "temporality": "current",
            },
        ],
        "red_flags": [],
        "needs_clarification": False,
        "clarification_question": None,
    }

    result = parse_extraction(f"```json\n{json.dumps(payload)}\n```")

    assert result.observations[0].fact == "cough"
    assert result.observations[0].status == "absent"
    assert result.observations[1].fact == "wheezing"


def test_parse_extraction_rejects_unknown_facts():
    payload = {
        "observations": [
            {
                "fact": "invented_disease",
                "status": "present",
                "subject": "patient",
                "temporality": "current",
            }
        ],
        "red_flags": [],
        "needs_clarification": False,
        "clarification_question": None,
    }

    with pytest.raises(ExtractionError):
        parse_extraction(json.dumps(payload))


def test_extract_observations_uses_validated_ollama_response():
    payload = {
        "observations": [
            {
                "fact": "cough",
                "status": "absent",
                "subject": "patient",
                "temporality": "current",
            }
        ],
        "red_flags": [],
        "needs_clarification": False,
        "clarification_question": None,
    }
    calls = []

    def fake_request(url, model, prompt, timeout):
        calls.append((url, model, prompt, timeout))
        return f"```json\n{json.dumps(payload)}\n```"

    result = extract_observations(
        "I do not have a cough",
        request_fn=fake_request,
    )

    assert result.observations[0].status == "absent"
    assert calls[0][0] == "http://127.0.0.1:11434"
    assert calls[0][1] == "gemma4:12b-mlx"
    assert "I do not have a cough" in calls[0][2]


def test_fallback_extractor_respects_negation_and_contrast():
    result = fallback_extract_observations(
        "I do not have a cough, but I feel dizzy and wheeze during exercise."
    )
    statuses = {item.fact: item.status for item in result.observations}

    assert statuses["cough"] == "absent"
    assert statuses["dizziness"] == "present"
    assert statuses["wheezing"] == "present"
    assert statuses["exercise_triggered"] == "present"


def test_fallback_extractor_conservative_boundaries():
    # Case 1: Compound negation
    result = fallback_extract_observations("no cough or wheezing")
    statuses = {item.fact: item.status for item in result.observations}
    assert statuses.get("cough") == "absent"
    assert statuses.get("wheezing") == "absent"

    # Case 2: Third-party attribution (Should be ignored by conservative fallback)
    result = fallback_extract_observations("my father has diabetes and a cough")
    statuses = {item.fact: item.status for item in result.observations}
    assert "diabetes" not in statuses

    # Case 3: No recognized symptoms
    result = fallback_extract_observations("I feel great, thanks for asking!")
    assert result.needs_clarification is True
    assert len(result.observations) == 0

    # Case 4: Temporal isolation (Conservative fallback usually treats all as current)
    result = fallback_extract_observations("I had a cough last year")
    statuses = {item.fact: item.status for item in result.observations}
    assert statuses.get("cough") == "present"
