% Non-interactive, data-only scoring engine for the Flask application.
%
% Input on stdin:
%   {"facts":["fatigue"], "diseases":["anemia"]}
%
% Output on stdout:
%   {"results":[{"disease":"anemia", "count":1, ...}]}
%
% The Python caller validates every atom against server-side allowlists before
% invoking this program. No client value is interpolated into Prolog source.

:- use_module(library(http/json)).
:- use_module(library(lists)).


question_fact(Question, Fact) :-
    split_string(Question, "|", "", [_, FactName]),
    atom_string(Fact, FactName).


matched_question_facts([], _, []).
matched_question_facts([Question|Rest], Facts, [Fact|Matched]) :-
    question_fact(Question, Fact),
    memberchk(Fact, Facts), !,
    matched_question_facts(Rest, Facts, Matched).
matched_question_facts([_|Rest], Facts, Matched) :-
    matched_question_facts(Rest, Facts, Matched).


score_disease(Disease, Facts, Result) :-
    disease(Disease, Threshold, Questions),
    matched_question_facts(Questions, Facts, Matched),
    length(Matched, Count),
    length(Questions, QuestionCount),
    ( Count >= Threshold -> Label = 'screen-positive'
    ; Label = 'not-qualified'
    ),
    Result = _{
        disease:Disease,
        label:Label,
        matched:Matched,
        count:Count,
        threshold:Threshold,
        question_count:QuestionCount
    }.


evaluate_diseases([], _, []).
evaluate_diseases([Disease|Rest], Facts, [Result|Results]) :-
    score_disease(Disease, Facts, Result),
    evaluate_diseases(Rest, Facts, Results).


strings_to_atoms([], []).
strings_to_atoms([String|Rest], [Atom|Atoms]) :-
    atom_string(Atom, String),
    strings_to_atoms(Rest, Atoms).


web_json_main :-
    json_read_dict(current_input, Input),
    strings_to_atoms(Input.facts, Facts),
    strings_to_atoms(Input.diseases, Diseases),
    evaluate_diseases(Diseases, Facts, Results),
    json_write_dict(current_output, _{results:Results}),
    nl.
