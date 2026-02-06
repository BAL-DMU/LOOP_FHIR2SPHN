"""
Tests for ConditionToProblemCondition.map

Tests the Condition (problem-list-item) -> ProblemCondition mapping including:
- code (ICD-10) -> hasCode
- recordedDate -> hasRecordDateTime
- encounter -> hasAdministrativeCase
- note.text -> hasStringValue
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_problem_condition(
    condition_id="cond-1",
    icd10_code=None,
    recorded_date=None,
    encounter_ref=None,
    note_text=None,
):
    """Create a Condition resource with problem-list-item category."""
    condition = {
        "resourceType": "Condition",
        "id": condition_id,
        "meta": {"source": "http://example.org/ehr"},
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "problem-list-item",
                    }
                ]
            }
        ],
        "subject": {"reference": "Patient/pat-1"},
    }

    if icd10_code:
        condition["code"] = {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": icd10_code}]
        }

    if recorded_date:
        condition["recordedDate"] = recorded_date

    if encounter_ref:
        condition["encounter"] = {"reference": encounter_ref}

    if note_text:
        condition["note"] = [{"text": note_text}]

    return condition


class TestProblemConditionBasic:
    """Test basic ProblemCondition creation."""

    def test_condition_creates_problem_condition(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Condition with problem-list-item category creates ProblemCondition."""
        condition = make_problem_condition(icd10_code="I10.9")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.ProblemCondition[0]")

    def test_problem_condition_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """ProblemCondition id is prefixed with 'Condition/'."""
        condition = make_problem_condition(condition_id="my-condition", icd10_code="I10.9")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.ProblemCondition[0].id", "Condition/my-condition")


class TestICD10Mapping:
    """Test ICD-10 code mapping."""

    def test_icd10_code_mapped(self, transform_bundle, make_bundle, base_patient):
        """ICD-10 code is correctly mapped to hasCode."""
        condition = make_problem_condition(icd10_code="J18.9")  # Pneumonia
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.ProblemCondition[0].hasCode")
        assert_path_equals(result, "content.ProblemCondition[0].hasCode.termid", "J18.9")

    def test_icd10_iri_format(self, transform_bundle, make_bundle, base_patient):
        """ICD-10 IRI uses biomedit.ch format."""
        condition = make_problem_condition(icd10_code="J18.9")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        iri = get_path(result, "content.ProblemCondition[0].hasCode.iri")
        assert iri == "https://biomedit.ch/rdf/sphn-resource/icd-10-gm/J18.9"

    def test_icd10_code_with_suffix_transformation(
        self, transform_bundle, make_bundle, base_patient
    ):
        """ICD-10 codes in cm-icd10 conceptmap get '-' suffix."""
        # I10.9 is in the conceptmap with '-' suffix transformation
        condition = make_problem_condition(icd10_code="I10.9")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        termid = get_path(result, "content.ProblemCondition[0].hasCode.termid")
        # The conceptmap transforms I10.9 to I10.9-
        assert termid == "I10.9-"

    def test_icd10_code_without_transformation(
        self, transform_bundle, make_bundle, base_patient
    ):
        """ICD-10 codes not in conceptmap are passed through."""
        # Use a code that's not in the conceptmap
        condition = make_problem_condition(icd10_code="A00.0")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        termid = get_path(result, "content.ProblemCondition[0].hasCode.termid")
        # A00.0 is not in the conceptmap, so it passes through unchanged
        assert termid == "A00.0"


class TestRecordedDate:
    """Test recordedDate -> hasRecordDateTime mapping."""

    def test_recorded_date_mapped(self, transform_bundle, make_bundle, base_patient):
        """Condition recordedDate maps to hasRecordDateTime."""
        condition = make_problem_condition(
            icd10_code="I10.9",
            recorded_date="2024-01-15T10:00:00Z",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.ProblemCondition[0].hasRecordDateTime",
            "2024-01-15T10:00:00Z",
        )


class TestEncounterReference:
    """Test encounter -> hasAdministrativeCase mapping."""

    def test_encounter_reference_mapped(self, transform_bundle, make_bundle, base_patient):
        """Condition encounter reference is mapped to hasAdministrativeCase."""
        condition = make_problem_condition(
            icd10_code="I10.9",
            encounter_ref="Encounter/enc-123",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.ProblemCondition[0].hasAdministrativeCase")
        assert admin_case is not None


class TestNoteText:
    """Test note.text -> hasStringValue mapping."""

    def test_note_text_mapped(self, transform_bundle, make_bundle, base_patient):
        """Condition note.text maps to hasStringValue."""
        condition = make_problem_condition(
            icd10_code="I10.9",
            note_text="Patient diagnosed with essential hypertension",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.ProblemCondition[0].hasStringValue",
            "Patient diagnosed with essential hypertension",
        )

    def test_no_note_no_string_value(self, transform_bundle, make_bundle, base_patient):
        """Condition without note has no hasStringValue."""
        condition = make_problem_condition(icd10_code="I10.9")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        string_value = get_path(result, "content.ProblemCondition[0].hasStringValue")
        assert string_value is None


class TestMultipleConditions:
    """Test multiple conditions in bundle."""

    def test_multiple_problem_conditions(self, transform_bundle, make_bundle, base_patient):
        """Multiple problem conditions create multiple ProblemConditions."""
        cond1 = make_problem_condition(condition_id="cond-1", icd10_code="I10.9")
        cond2 = make_problem_condition(condition_id="cond-2", icd10_code="E11.9")
        bundle = make_bundle(base_patient, cond1, cond2)

        result = transform_bundle(bundle)

        conditions = get_path(result, "content.ProblemCondition")
        assert conditions is not None
        assert len(conditions) == 2
