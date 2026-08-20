% AUTO-GENERATED from diseases.yaml — do not edit directly

symptom_diseases(headache, [hypertension, anemia]).
symptom_diseases(elevated_bp, [hypertension, diabetes]).
symptom_diseases(chest_pain, [hypertension, anemia]).
symptom_diseases(fatigue, [anemia, diabetes, hypertension]).
symptom_diseases(pale_skin, [anemia]).
symptom_diseases(dizziness, [anemia, hypertension]).
symptom_diseases(polyuria, [diabetes, uti]).
symptom_diseases(polydipsia, [diabetes]).
symptom_diseases(elevated_glucose, [diabetes, hypertension]).
symptom_diseases(nausea, [diabetes, anemia]).
symptom_diseases(dysuria, [uti]).
symptom_diseases(urinary_frequency, [uti, diabetes]).
symptom_diseases(cough, [asthma, tuberculosis]).
symptom_diseases(shortness_of_breath, [asthma, tuberculosis, anemia]).
symptom_diseases(fever, [tuberculosis, uti]).
symptom_diseases(night_sweats, [tuberculosis]).
symptom_diseases(weight_loss, [tuberculosis, diabetes]).
symptom_diseases(other, [diabetes, hypertension, anemia, uti, asthma, tuberculosis]).

first_disease_to_check(headache, hypertension).
first_disease_to_check(elevated_bp, hypertension).
first_disease_to_check(chest_pain, hypertension).
first_disease_to_check(fatigue, anemia).
first_disease_to_check(pale_skin, anemia).
first_disease_to_check(dizziness, anemia).
first_disease_to_check(polyuria, diabetes).
first_disease_to_check(polydipsia, diabetes).
first_disease_to_check(elevated_glucose, diabetes).
first_disease_to_check(nausea, diabetes).
first_disease_to_check(dysuria, uti).
first_disease_to_check(urinary_frequency, uti).
first_disease_to_check(cough, asthma).
first_disease_to_check(shortness_of_breath, asthma).
first_disease_to_check(fever, tuberculosis).
first_disease_to_check(night_sweats, tuberculosis).
first_disease_to_check(weight_loss, tuberculosis).
first_disease_to_check(other, diabetes).