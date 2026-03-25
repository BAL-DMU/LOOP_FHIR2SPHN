"""
Tests for ConditionToNursingDiagnosis.map

Tests the Condition (nanda-nursing-diagnosis) -> NursingDiagnosis mapping including:
- code (NANDA) -> hasCode
- recordedDate -> hasRecordDateTime
- encounter -> hasAdministrativeCase
- onsetAge -> hasSubjectAge with Age resource
"""

import pytest

from tests.helpers import (
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_nursing_diagnosis(
    condition_id="nursing-1",
    nanda_code=None,
    nanda_display=None,
    recorded_date=None,
    encounter_ref=None,
    onset_age_value=None,
    onset_age_unit=None,
):
    """Create a Condition resource with nanda-nursing-diagnosis category."""
    condition = {
        "resourceType": "Condition",
        "id": condition_id,
        "meta": {"source": "http://example.org/ehr"},
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "nanda-nursing-diagnosis",
                    }
                ]
            }
        ],
        "subject": {"reference": "Patient/pat-1"},
    }

    if nanda_code:
        coding = {
            "system": "http://terminology.hl7.org/CodeSystem/nanda",
            "code": nanda_code,
        }
        if nanda_display:
            coding["display"] = nanda_display
        condition["code"] = {"coding": [coding]}

    if recorded_date:
        condition["recordedDate"] = recorded_date

    if encounter_ref:
        condition["encounter"] = {"reference": encounter_ref}

    if onset_age_value is not None:
        condition["onsetAge"] = {
            "value": onset_age_value,
            "unit": onset_age_unit or "a",
            "system": "http://unitsofmeasure.org",
            "code": onset_age_unit or "a",
        }

    return condition


class TestNursingDiagnosisBasic:
    """Test basic NursingDiagnosis creation."""

    def test_condition_creates_nursing_diagnosis(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Condition with nanda-nursing-diagnosis category creates NursingDiagnosis."""
        condition = make_nursing_diagnosis(nanda_code="00046")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.NursingDiagnosis[0]")

    def test_nursing_diagnosis_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """NursingDiagnosis id is prefixed with 'Condition/'."""
        condition = make_nursing_diagnosis(condition_id="my-nursing", nanda_code="00046")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.NursingDiagnosis[0].id", "Condition/my-nursing")


class TestNANDACodeMapping:
    """Test NANDA code mapping."""

    def test_nanda_code_mapped_as_identifier(
        self, transform_bundle, make_bundle, base_patient
    ):
        """NANDA code is mapped to hasCode.hasIdentifier."""
        condition = make_nursing_diagnosis(nanda_code="00046")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.NursingDiagnosis[0].hasCode")
        assert_path_equals(
            result, "content.NursingDiagnosis[0].hasCode.hasIdentifier", "00046"
        )

    def test_nanda_system_mapped(self, transform_bundle, make_bundle, base_patient):
        """NANDA coding system is mapped to hasCodingSystemAndVersion."""
        condition = make_nursing_diagnosis(nanda_code="00046")
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.NursingDiagnosis[0].hasCode.hasCodingSystemAndVersion",
            "http://terminology.hl7.org/CodeSystem/nanda",
        )

    def test_nanda_display_mapped(self, transform_bundle, make_bundle, base_patient):
        """NANDA display is mapped to hasCode.hasName."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            nanda_display="Impaired skin integrity",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.NursingDiagnosis[0].hasCode.hasName",
            "Impaired skin integrity",
        )


class TestRecordedDate:
    """Test recordedDate -> hasRecordDateTime mapping."""

    def test_recorded_date_mapped(self, transform_bundle, make_bundle, base_patient):
        """NursingDiagnosis recordedDate maps to hasRecordDateTime."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            recorded_date="2024-01-20T09:00:00Z",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.NursingDiagnosis[0].hasRecordDateTime",
            "2024-01-20T09:00:00Z",
        )


class TestEncounterReference:
    """Test encounter -> hasAdministrativeCase mapping."""

    def test_encounter_reference_mapped(self, transform_bundle, make_bundle, base_patient):
        """NursingDiagnosis encounter reference is mapped."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            encounter_ref="Encounter/enc-456",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.NursingDiagnosis[0].hasAdministrativeCase")
        assert admin_case is not None


class TestOnsetAge:
    """Test onsetAge -> hasSubjectAge with Age resource mapping."""

    def test_onset_age_creates_age_resource(
        self, transform_bundle, make_bundle, base_patient
    ):
        """onsetAge creates Age resource in Content."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            onset_age_value=65,
            onset_age_unit="a",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        # Age resource should be created in content
        ages = get_path(result, "content.Age")
        assert ages is not None
        assert len(ages) >= 1

    def test_onset_age_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """onsetAge value is correctly mapped to Age.hasQuantity."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            onset_age_value=65,
            onset_age_unit="a",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        ages = get_path(result, "content.Age")
        assert ages is not None

        # Find the Age with the correct value
        for age in ages:
            quantity = get_path(age, "hasQuantity")
            if quantity and quantity.get("hasValue") == 65:
                return  # Test passes

        pytest.fail("Age with value 65 not found")

    def test_nursing_diagnosis_references_age(
        self, transform_bundle, make_bundle, base_patient
    ):
        """NursingDiagnosis hasSubjectAge references the Age resource."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            onset_age_value=65,
            onset_age_unit="a",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        subject_age = get_path(result, "content.NursingDiagnosis[0].hasSubjectAge")
        assert subject_age is not None

    def test_age_determination_datetime_from_recorded(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Age hasDeterminationDateTime comes from recordedDate."""
        condition = make_nursing_diagnosis(
            nanda_code="00046",
            onset_age_value=65,
            onset_age_unit="a",
            recorded_date="2024-01-20T09:00:00Z",
        )
        bundle = make_bundle(base_patient, condition)

        result = transform_bundle(bundle)

        ages = get_path(result, "content.Age")
        assert ages is not None

        # Find the Age with determination datetime
        for age in ages:
            if age.get("hasDeterminationDateTime") == "2024-01-20T09:00:00Z":
                return  # Test passes

        pytest.fail("Age with determination datetime not found")


class TestMultipleNursingDiagnoses:
    """Test multiple nursing diagnoses in bundle."""

    def test_multiple_nursing_diagnoses(self, transform_bundle, make_bundle, base_patient):
        """Multiple nursing diagnoses create multiple NursingDiagnosis entries."""
        diag1 = make_nursing_diagnosis(condition_id="nursing-1", nanda_code="00046")
        diag2 = make_nursing_diagnosis(condition_id="nursing-2", nanda_code="00047")
        bundle = make_bundle(base_patient, diag1, diag2)

        result = transform_bundle(bundle)

        diagnoses = get_path(result, "content.NursingDiagnosis")
        assert diagnoses is not None
        assert len(diagnoses) == 2
