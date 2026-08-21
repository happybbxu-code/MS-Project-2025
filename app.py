"""
Medical Diagnosis Chat — Flask + Prolog (no API key needed)

Symptom extraction:  keyword rules (rule-based NLP)
Diagnosis decision:  SWI-Prolog production rules
Doctor responses:    templated strings

Run:
    python3 app.py
Then open http://localhost:8080
"""

import os
import json
import subprocess
import re
import secrets
import threading
import time

import yaml
from flask import Flask, request, jsonify, send_from_directory

from llm_extractor import (
    ALLOWED_FACTS,
    ExtractionError,
    extract_observations,
    fallback_extract_observations,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))

import generate_prolog
generate_prolog.generate()

with open(os.path.join(BASE, 'diseases.yaml')) as f:
    CONFIG = yaml.safe_load(f)

ALL_DISEASES   = list(CONFIG['diseases'].keys())
SYMPTOM_ROUTING = CONFIG['symptom_routing']

app = Flask(__name__, static_folder='static')

SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_SECONDS', '3600'))
SESSIONS = {}
SESSION_LOCK = threading.RLock()


def _new_session():
    now = time.time()
    return {
        'facts': set(),
        'absent': set(),
        'uncertain': set(),
        'asked': set(),
        'disease_order': list(ALL_DISEASES),
        'pending_fact': None,
        'pending_question': None,
        'introduced': set(),
        'last_intro': None,
        'done': False,
        'created_at': now,
        'updated_at': now,
    }


def _create_session():
    session_id = secrets.token_urlsafe(32)
    with SESSION_LOCK:
        SESSIONS[session_id] = _new_session()
    return session_id


def _get_session(session_id):
    if not isinstance(session_id, str):
        return None
    now = time.time()
    with SESSION_LOCK:
        session = SESSIONS.get(session_id)
        if session is None:
            return None
        if now - session['updated_at'] > SESSION_TTL_SECONDS:
            del SESSIONS[session_id]
            return None
        session['updated_at'] = now
        return session


def apply_extraction(session, extraction):
    """Apply only current observations about the patient to server state."""
    for observation in extraction.observations:
        if observation.subject != 'patient' or observation.temporality != 'current':
            continue

        fact = observation.fact
        session['asked'].add(fact)
        if observation.status == 'present':
            session['facts'].add(fact)
            session['absent'].discard(fact)
            session['uncertain'].discard(fact)
        elif observation.status == 'absent':
            session['facts'].discard(fact)
            session['absent'].add(fact)
            session['uncertain'].discard(fact)
        else:
            session['facts'].discard(fact)
            session['absent'].discard(fact)
            session['uncertain'].add(fact)


# ---------------------------------------------------------------------------
# Keyword-based symptom extraction  (no API needed)
# ---------------------------------------------------------------------------

SYMPTOM_KEYWORDS = {
    'fatigue':               ['tired', 'fatigue', 'exhausted', 'weak', 'weakness', 'lethargic', 'no energy'],
    'headache':              ['headache', 'head ache', 'head pain', 'migraine', 'head hurts'],
    'elevated_bp':           ['high blood pressure', 'high bp', 'elevated bp', 'hypertension', 'blood pressure high'],
    'elevated_glucose':      ['high blood sugar', 'high glucose', 'elevated glucose', 'blood sugar', 'sugar level'],
    'polyuria':              ['urinating a lot', 'pee a lot', 'urinate often', 'frequent urination', 'urinating more'],
    'polydipsia':            ['very thirsty', 'always thirsty', 'excessive thirst', 'drinking a lot of water'],
    'pale_skin':             ['pale', 'pale skin', 'pallor', 'skin looks pale', 'look pale'],
    'dizziness':             ['dizzy', 'dizziness', 'lightheaded', 'light headed', 'spinning'],
    'dysuria':               ['burning when i urinate', 'burning urination', 'pain urinating', 'painful urination',
                              'burning pee', 'stinging urination'],
    'urinary_frequency':     ['urinate frequently', 'frequent urination', 'bathroom often', 'pee often', 'need to urinate'],
    'cough':                 ['cough', 'coughing'],
    'shortness_of_breath':   ['short of breath', 'shortness of breath', 'breathless', 'hard to breathe',
                              'difficulty breathing', 'out of breath'],
    'fever':                 ['fever', 'high temperature', 'high temp', 'temperature', 'running a fever'],
    'night_sweats':          ['night sweats', 'sweating at night', 'sweat at night', 'wake up sweating'],
    'weight_loss':           ['lost weight', 'weight loss', 'losing weight', 'dropped weight'],
    'nausea':                ['nausea', 'nauseous', 'feel sick', 'queasy', 'want to vomit'],
    'chest_pain':            ['chest pain', 'chest hurts', 'chest ache', 'pain in chest'],
    'persistent_cough':      ['cough for weeks', 'weeks of coughing', 'long cough', 'cough that wont go away'],
    'chronic_cough':         ['cough at night', 'cough worse at night', 'night cough', 'recurring cough'],
    'wheezing':              ['wheeze', 'wheezing', 'whistling breath', 'whistling sound breathing'],
}

YES_WORDS = ['yes', 'yeah', 'yep', 'yup', 'correct', 'right', 'sure', 'absolutely',
             'definitely', 'i do', 'i have', 'that is right', "that's right", 'indeed',
             'true', 'exactly', 'positive', 'affirmative', 'of course']

# Partial answers that lean yes — medically safer to count these as confirmed
PARTIAL_YES = ['sometimes', 'a bit', 'little', 'kind of', 'sort of', 'slightly',
               'occasionally', 'at times', 'now and then', 'mild', 'mildly',
               'somewhat', 'i think so', 'maybe yes', 'probably']

NO_WORDS = ['no', 'nope', 'nah', 'not really', "don't", 'dont', 'never', 'negative',
            'i do not', "i don't", 'i have not', "i haven't", 'false', 'incorrect',
            'not at all', 'absolutely not']

# These mean "I don't know" — should NOT count as no
UNSURE_PATTERNS = ['not sure', "don't know", 'dont know', 'no test', 'not tested',
                   "haven't tested", 'not taken', 'unknown', 'no idea', 'unsure',
                   'not checked', 'never checked', 'no result', 'yet to']


def extract_symptoms(text):
    """Return list of symptom atoms found in free text via keyword matching."""
    tl = text.lower()
    found = []
    for fact, keywords in SYMPTOM_KEYWORDS.items():
        for kw in keywords:
            if kw in tl:
                found.append(fact)
                break
    return found


def _has_phrase(text, phrase):
    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, text) is not None


def detect_yes_no(text):
    """
    Return 'yes', 'no', 'unsure', or 'unrecognized'.

    Uncertainty is checked first, followed by explicit negatives. This ordering
    prevents broad positive phrases such as "i do" or "absolutely" from
    reversing answers such as "I do not" or "absolutely not".
    """
    normalized = re.sub(r"\\s+", " ", text.lower().strip())

    if any(_has_phrase(normalized, phrase) for phrase in UNSURE_PATTERNS):
        return 'unsure'

    if any(_has_phrase(normalized, phrase) for phrase in NO_WORDS):
        return 'no'
    if re.search(r"\bnot\b", normalized):
        return 'no'

    if any(_has_phrase(normalized, phrase) for phrase in PARTIAL_YES):
        return 'yes'
    if any(_has_phrase(normalized, phrase) for phrase in YES_WORDS):
        return 'yes'

    return 'unrecognized'


def disease_order_for(confirmed_facts):
    """Merge every symptom route, prioritizing the most specific routes."""
    routed_facts = [
        fact for fact in confirmed_facts
        if fact in SYMPTOM_ROUTING and fact != 'other'
    ]
    routed_facts.sort(key=lambda fact: (len(SYMPTOM_ROUTING[fact]), fact))

    ordered = []
    for fact in routed_facts:
        for disease in SYMPTOM_ROUTING[fact]:
            if disease not in ordered:
                ordered.append(disease)

    return ordered or list(ALL_DISEASES)


def detect_emergency(text, facts, red_flags):
    """Apply deterministic red-flag escalation before routine screening."""
    normalized = text.lower()
    severe_flags = {
        'severe_chest_pain',
        'severe_shortness_of_breath',
        'loss_of_consciousness',
        'stroke_symptoms',
    }
    severe_language = any(phrase in normalized for phrase in (
        'crushing chest pain',
        'severe chest pain',
        "can't breathe",
        'cannot breathe',
        'cannot catch my breath',
        'passed out',
        'unconscious',
        'face drooping',
        'slurred speech',
    ))
    if severe_language or severe_flags.intersection(red_flags):
        return {
            'type': 'emergency',
            'message': (
                'Your description may indicate a medical emergency. '
                'Please contact emergency services now or go to the nearest '
                'emergency department. Do not rely on this screening tool.'
            ),
        }

    if 'coughing_blood' in facts or 'coughing_blood' in red_flags:
        return {
            'type': 'urgent',
            'message': (
                'Coughing up blood needs urgent medical evaluation. Please '
                'contact a clinician or urgent service immediately.'
            ),
        }
    return None


# ---------------------------------------------------------------------------
# Prolog bridge
# ---------------------------------------------------------------------------

def next_question(session):
    """Return and record the next unresolved question across all candidates."""
    for disease in session['disease_order']:
        for item in CONFIG['diseases'][disease]['questions']:
            fact = item['fact']
            if fact in session['asked']:
                continue
            session['pending_fact'] = fact
            session['pending_question'] = item['text']
            session['last_intro'] = disease
            return {
                'disease': disease,
                'fact': fact,
                'question': item['text'],
            }
    session['pending_fact'] = None
    session['pending_question'] = None
    return None


def question_message(session, question):
    parts = []
    disease = question['disease']
    if disease not in session['introduced']:
        intro = DISEASE_INTRO.get(disease)
        if intro:
            parts.append(intro)
        session['introduced'].add(disease)
    parts.append(question['question'])
    return '\n\n'.join(parts)


def run_prolog(facts, disease_order):
    """Score allowlisted facts through Prolog using JSON stdin/stdout only."""
    fact_set = set(facts)
    if not fact_set <= ALLOWED_FACTS:
        return {'type': 'error', 'detail': 'invalid fact supplied to Prolog'}
    if any(disease not in ALL_DISEASES for disease in disease_order):
        return {'type': 'error', 'detail': 'invalid disease supplied to Prolog'}

    payload = json.dumps({
        'facts': sorted(fact_set),
        'diseases': list(dict.fromkeys(disease_order)),
    })
    command = [
        'swipl', '-q',
        '-s', os.path.join(BASE, 'generated', 'diseases.pl'),
        '-s', os.path.join(BASE, 'web_engine.pl'),
        '-g', 'web_json_main',
        '-t', 'halt',
    ]
    try:
        completed = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {'type': 'error', 'detail': 'Prolog timed out'}

    if completed.returncode != 0:
        return {'type': 'error', 'detail': completed.stderr[:300]}
    try:
        raw_results = json.loads(completed.stdout).get('results', [])
    except json.JSONDecodeError:
        return {'type': 'error', 'detail': 'invalid Prolog response'}

    qualified = [
        item for item in raw_results
        if item.get('label') == 'screen-positive'
    ]
    qualified.sort(
        key=lambda item: (
            -(item['count'] / item['threshold']),
            -item['count'],
            item['disease'],
        )
    )
    if not qualified:
        return {'type': 'no_match', 'assessments': raw_results}
    return {
        'type': 'screening',
        'candidates': qualified,
        'assessments': raw_results,
    }


# ---------------------------------------------------------------------------
# Templated doctor responses  (no API needed)
# ---------------------------------------------------------------------------

WELCOME = (
    "Hello! I'm glad you came in today. I'm here to help figure out "
    "what might be going on with your health.\n\n"
    "Can you tell me what has been bothering you the most lately? "
    "Feel free to describe your symptoms in your own words."
)

DISEASE_INTRO = {
    'diabetes':     "I see. Let me ask you a few questions about your blood sugar levels and some related symptoms.",
    'hypertension': "Let me check a few things related to your blood pressure.",
    'anemia':       "Alright. I'd like to ask some questions about possible signs of low blood count.",
    'uti':          "Okay. I would like to ask you about your urinary symptoms.",
    'asthma':       "Given what you've mentioned, let me check whether this could be related to your airways.",
    'tuberculosis': "I want to rule out one more thing that can cause persistent respiratory symptoms.",
}


def doctor_response_for(prolog_result):
    rtype = prolog_result['type']

    if rtype == 'screening':
        lines = []
        for candidate in prolog_result['candidates']:
            disease = candidate['disease'].replace('_', ' ').title()
            matched = ', '.join(
                fact.replace('_', ' ') for fact in candidate['matched']
            ) or 'no reported matching observations'
            lines.append(
                f"- {disease}: screening score "
                f"{candidate['count']}/{candidate['threshold']} "
                f"(matched: {matched})"
            )
        return (
            "This screening found patterns that may be associated with:\n\n"
            + '\n'.join(lines)
            + "\n\nThis is not a confirmed diagnosis. These symptom-count rules "
              "cannot replace measurements, laboratory testing, physical "
              "examination, or evaluation by a qualified clinician."
        )

    if rtype == 'no_match':
        return (
            "This limited screening did not find enough matching observations "
            "for its configured conditions. It does not rule out illness or "
            "evaluate every possible cause. Please seek clinical evaluation "
            "if symptoms persist, worsen, or concern you."
        )

    return (
        "The screening engine could not complete safely. "
        f"({prolog_result.get('detail', 'unknown error')})"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/start', methods=['POST'])
def start():
    session_id = _create_session()
    return jsonify({
        'message': WELCOME,
        'session_id': session_id,
        'done': False,
    })


@app.route('/chat', methods=['POST'])
def chat():
    body = request.get_json(silent=True) or {}
    user_message = body.get('message')
    session = _get_session(body.get('session_id'))
    if session is None:
        return jsonify({'error': 'invalid or expired session'}), 404
    if not isinstance(user_message, str) or not user_message.strip():
        return jsonify({'error': 'message must be non-empty text'}), 400
    user_message = user_message.strip()[:4000]

    pending_fact = session.get('pending_fact')
    pending_question = session.get('pending_question')
    red_flags = set()

    if pending_fact:
        answer = detect_yes_no(user_message)
        if answer == 'unrecognized':
            return jsonify({
                'message': (
                    "I could not reliably classify that answer. Please answer "
                    "yes, no, or not sure.\n\n" + (pending_question or '')
                ),
                'session_id': body['session_id'],
                'done': False,
            })

        session['asked'].add(pending_fact)
        if answer == 'yes':
            session['facts'].add(pending_fact)
            session['absent'].discard(pending_fact)
            session['uncertain'].discard(pending_fact)
        elif answer == 'no':
            session['facts'].discard(pending_fact)
            session['absent'].add(pending_fact)
            session['uncertain'].discard(pending_fact)
        else:
            session['facts'].discard(pending_fact)
            session['absent'].discard(pending_fact)
            session['uncertain'].add(pending_fact)
        session['pending_fact'] = None
        session['pending_question'] = None
    else:
        try:
            extraction = extract_observations(user_message)
        except ExtractionError:
            extraction = fallback_extract_observations(user_message)

        if extraction.needs_clarification:
            if extraction.is_general_query:
                next_q = next_question(session)
                if next_q:
                    return jsonify({
                        'message': question_message(session, next_q),
                        'session_id': body['session_id'],
                        'done': False,
                    })
                else:
                    return jsonify({
                        'message': 'How can I help you? Please describe any symptoms you are feeling.',
                        'session_id': body['session_id'],
                        'done': False,
                    })
            else:
                return jsonify({
                    'message': extraction.clarification_question or (
                        'Could you clarify which symptoms you currently have?'
                    ),
                    'session_id': body['session_id'],
                    'done': False,
                })
        apply_extraction(session, extraction)
        red_flags.update(extraction.red_flags)

    triage = detect_emergency(user_message, session['facts'], red_flags)
    if triage:
        session['done'] = True
        return jsonify({
            'message': triage['message'],
            'session_id': body['session_id'],
            'done': True,
            'result': triage,
        })

    session['disease_order'] = disease_order_for(session['facts'])
    question = next_question(session)
    if question:
        return jsonify({
            'message': question_message(session, question),
            'session_id': body['session_id'],
            'done': False,
        })

    result = run_prolog(session['facts'], session['disease_order'])
    session['done'] = True
    return jsonify({
        'message': doctor_response_for(result),
        'session_id': body['session_id'],
        'done': True,
        'result': result,
    })


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print('\nStarting Medical Diagnosis Chat at http://localhost:8080\n')
    app.run(debug=False, port=8080)
