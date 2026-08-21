import pytest

import app
from llm_extractor import ExtractionResult, Observation


@pytest.fixture(autouse=True)
def clear_sessions():
    app.SESSIONS.clear()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", "yes"),
        ("absolutely not", "no"),
        ("not correct", "no"),
        ("no, that is not right", "no"),
        ("I do not have wheezing", "no"),
        ("not sure", "unsure"),
        ("sometimes", "yes"),
        ("unrelated words", "unrecognized"),
    ],
)
def test_detect_yes_no_respects_negation(text, expected):
    assert app.detect_yes_no(text) == expected


def test_detect_yes_no_preserves_uncertainty():
    # 'not sure' should be 'unsure', not 'no'
    assert app.detect_yes_no("I'm not sure") == "unsure"
    assert app.detect_yes_no("i dont know") == "unsure"


def test_detect_yes_no_handles_unrelated_text():
    assert app.detect_yes_no("The weather is nice today") == "unrecognized"
    assert app.detect_yes_no("I like apples") == "unrecognized"


def test_start_uses_server_side_session_identifier():
    client = app.app.test_client()

    response = client.post("/start")
    body = response.get_json()

    assert response.status_code == 200
    assert isinstance(body["session_id"], str)
    assert len(body["session_id"]) >= 32
    assert "session" not in body
    # Explicitly verify that the session was created in the server's state
    assert body["session_id"] in app.SESSIONS


def test_chat_rejects_unknown_server_session():
    client = app.app.test_client()

    response = client.post(
        "/chat",
        json={"session_id": "not-a-real-session", "message": "cough"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "invalid or expired session"


def test_chat_ignores_client_injected_session_data(monkeypatch):
    # Mock extraction to ensure we reach the point where session is updated
    extraction = ExtractionResult(
        observations=[],
        red_flags=[],
        needs_clarification=False,
        clarification_question=None,
    )
    monkeypatch.setattr(app, "extract_observations", lambda _: extraction)
    
    client = app.app.test_client()
    started = client.post("/start").get_json()
    session_id = started["session_id"]
    
    # Attempt to inject facts via a 'session' key in the request body
    client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "I feel fine",
            "session": {
                "facts": ["cough", "fever"],
                "asked": [],
            },
        },
    )
    
    server_session = app._get_session(session_id)
    # The server session should still be empty (only the empty extraction applied)
    assert "cough" not in server_session["facts"]
    assert "fever" not in server_session["facts"]


def test_disease_order_merges_routes_from_all_confirmed_symptoms():
    order = app.disease_order_for({"dysuria", "cough"})

    assert order[0] == "uti"
    assert set(order) == {"uti", "asthma", "tuberculosis"}


def test_prolog_returns_all_qualifying_screening_candidates():
    result = app.run_prolog(
        {
            "fatigue",
            "pale_skin",
            "elevated_glucose",
            "high_hba1c",
            "polyuria",
        },
        ["anemia", "diabetes"],
    )

    assert result["type"] == "screening"
    assert [item["disease"] for item in result["candidates"]] == [
        "diabetes",
        "anemia",
    ]
    assert all(item["label"] == "screen-positive" for item in result["candidates"])


def test_emergency_triage_precedes_routine_rules():
    triage = app.detect_emergency(
        "I have crushing chest pain and cannot catch my breath",
        {"chest_pain", "shortness_of_breath"},
        {"severe_chest_pain", "severe_shortness_of_breath"},
    )

    assert triage["type"] == "emergency"
    assert "emergency services" in triage["message"].lower()


def test_emergency_triage_triggers_immediate_done(monkeypatch):
    client = app.app.test_client()
    
    # Case 1: Severe language
    started = client.post("/start").get_json()
    session_id = started["session_id"]
    
    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "I have crushing chest pain",
        },
    )
    body = response.get_json()
    assert body["done"] is True
    assert "emergency services" in body["message"].lower()
    
    # Case 2: Red flags via LLM extraction
    session_id_2 = client.post("/start").get_json()["session_id"]
    
    extraction = ExtractionResult(
        observations=[],
        red_flags=["severe_chest_pain"],
        needs_clarification=False,
        clarification_question=None,
    )
    monkeypatch.setattr(app, "extract_observations", lambda _: extraction)
    
    response = client.post(
        "/chat",
        json={
            "session_id": session_id_2,
            "message": "Something is wrong",
        },
    )
    body = response.get_json()
    assert body["done"] is True
    assert "emergency services" in body["message"].lower()

def test_urgent_triage_triggers_correctly(monkeypatch):
    client = app.app.test_client()
    session_id = client.post("/start").get_json()["session_id"]
    
    extraction = ExtractionResult(
        observations=[],
        red_flags=["coughing_blood"],
        needs_clarification=False,
        clarification_question=None,
    )
    monkeypatch.setattr(app, "extract_observations", lambda _: extraction)
    
    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "I am coughing up blood",
        },
    )
    body = response.get_json()
    assert body["done"] is True
    assert "urgent medical evaluation" in body["message"].lower()


def test_apply_extraction_tracks_polarity_subject_and_temporality():
    session = app._new_session()
    session["facts"].add("cough")
    extraction = ExtractionResult(
        observations=[
            Observation(
                fact="cough",
                status="absent",
                subject="patient",
                temporality="current",
            ),
            Observation(
                fact="wheezing",
                status="present",
                subject="patient",
                temporality="current",
            ),
            Observation(
                fact="elevated_glucose",
                status="present",
                subject="family_member",
                temporality="current",
            ),
            Observation(
                fact="chest_pain",
                status="present",
                subject="patient",
                temporality="historical",
            ),
        ],
        red_flags=[],
        needs_clarification=False,
        clarification_question=None,
    )

    app.apply_extraction(session, extraction)

    assert "cough" not in session["facts"]
    assert "cough" in session["absent"]
    assert "wheezing" in session["facts"]
    assert "elevated_glucose" not in session["facts"]
    assert "chest_pain" not in session["facts"]


def test_next_question_skips_already_resolved_facts():
    session = app._new_session()
    session["disease_order"] = ["anemia"]
    session["facts"].add("fatigue")
    session["asked"].add("fatigue")

    question = app.next_question(session)

    assert question["fact"] == "pale_skin"
    assert "skin" in question["question"].lower()


def test_next_question_handles_all_resolved():
    session = app._new_session()
    session["disease_order"] = ["anemia"]
    # Mark all questions for anemia as asked
    for item in app.CONFIG["diseases"]["anemia"]["questions"]:
        session["asked"].add(item["fact"])

    question = app.next_question(session)
    assert question is None


def test_next_question_respects_disease_order():
    session = app._new_session()
    session["disease_order"] = ["uti", "anemia"]
    
    # Should pick the first question of the first disease in order
    question = app.next_question(session)
    assert question["disease"] == "uti"
    
    # After UTI is exhausted, should move to anemia
    for item in app.CONFIG["diseases"]["uti"]["questions"]:
        session["asked"].add(item["fact"])
        
    question = app.next_question(session)
    assert question["disease"] == "anemia"


def test_prolog_injection_resistance(monkeypatch):
    # Attempt to inject Prolog code via a forged fact name
    # Since run_prolog validates against ALLOWED_FACTS, this should be caught
    malicious_facts = {"cough'; halt; %"}
    disease_order = ["anemia"]
    
    result = app.run_prolog(malicious_facts, disease_order)
    
    assert result["type"] == "error"
    assert "invalid fact" in result["detail"]


def test_screening_response_is_non_diagnostic_and_lists_all_candidates():
    result = {
        "type": "screening",
        "candidates": [
            {
                "disease": "diabetes",
                "matched": ["elevated_glucose", "polyuria", "polydipsia"],
                "count": 3,
                "threshold": 3,
                "label": "screen-positive",
            },
            {
                "disease": "anemia",
                "matched": ["fatigue", "pale_skin"],
                "count": 2,
                "threshold": 2,
                "label": "screen-positive",
            },
        ],
    }

    message = app.doctor_response_for(result)

    assert "screening" in message.lower()
    assert "not a confirmed diagnosis" in message.lower()
    assert "diabetes" in message.lower()
    assert "anemia" in message.lower()


def test_chat_uses_server_state_and_llm_extraction(monkeypatch):
    extraction = ExtractionResult(
        observations=[
            Observation(
                fact="cough",
                status="present",
                subject="patient",
                temporality="current",
            )
        ],
        red_flags=[],
        needs_clarification=False,
        clarification_question=None,
    )
    monkeypatch.setattr(app, "extract_observations", lambda _: extraction)
    client = app.app.test_client()
    started = client.post("/start").get_json()

    response = client.post(
        "/chat",
        json={
            "session_id": started["session_id"],
            "message": "I have a cough",
            "session": {
                "facts": ["x)).\n:- writeln('INJECTED').\n%"],
            },
        },
    )
    body = response.get_json()
    session = app._get_session(started["session_id"])

    assert response.status_code == 200
    assert "session" not in body
    assert body["session_id"] == started["session_id"]
    assert session["facts"] == {"cough"}
    assert session["pending_fact"] == "chronic_cough"
    assert "recurring cough" in body["message"].lower()


def test_general_query_with_no_symptoms_advances_to_next_question(monkeypatch):
    # A non-symptomatic message (e.g. a greeting) must not loop; it should
    # move on to the next pending question or produce a polite fallback.
    extraction = ExtractionResult(
        observations=[],
        red_flags=[],
        needs_clarification=True,
        is_general_query=True,
        clarification_question=None,
    )
    monkeypatch.setattr(app, "extract_observations", lambda _: extraction)
    client = app.app.test_client()
    session_id = client.post("/start").get_json()["session_id"]

    response = client.post(
        "/chat",
        json={"session_id": session_id, "message": "How are you?"},
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["done"] is False
    # It must not loop on the repeating symptom-clarification prompt.
    assert "more specifically" not in body["message"].lower()


def test_pending_negative_answer_is_not_reextracted(monkeypatch):
    extraction = ExtractionResult(
        observations=[
            Observation(
                fact="cough",
                status="present",
                subject="patient",
                temporality="current",
            )
        ],
        red_flags=[],
        needs_clarification=False,
        clarification_question=None,
    )
    calls = []

    def fake_extract(text):
        calls.append(text)
        return extraction

    monkeypatch.setattr(app, "extract_observations", fake_extract)
    client = app.app.test_client()
    session_id = client.post("/start").get_json()["session_id"]
    client.post(
        "/chat",
        json={"session_id": session_id, "message": "I have a cough"},
    )

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "I do not have chronic cough",
        },
    )
    session = app._get_session(session_id)

    assert response.status_code == 200
    assert calls == ["I have a cough"]
    assert "chronic_cough" not in session["facts"]
    assert "chronic_cough" in session["absent"]
    assert session["pending_fact"] == "chest_tightness"
