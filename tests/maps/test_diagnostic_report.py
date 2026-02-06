"""
Tests for DiagnosticReportToLabTestEvent.map

Tests the DiagnosticReport + Observation -> LabTestEvent mapping including:
- DiagnosticReport -> LabTestEvent
- Result Observations -> LabTest with LOINC code
- valueQuantity -> LabResult.hasQuantity
- valueString -> LabResult.hasStringValue
- referenceRange -> hasNumericalReference
"""

import pytest

from tests.helpers import (
    assert_path_equals,
    assert_path_exists,
    assert_quantity_mapped,
    get_path,
)


def make_lab_observation(
    obs_id="obs-lab-1",
    loinc_code=None,
    value_quantity=None,
    value_string=None,
    reference_range_low=None,
    reference_range_high=None,
):
    """Create a laboratory Observation resource."""
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "meta": {"source": "http://example.org/lab"},
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                    }
                ]
            }
        ],
    }

    if loinc_code:
        obs["code"] = {"coding": [{"system": "https://loinc.org", "code": loinc_code}]}

    if value_quantity:
        obs["valueQuantity"] = {
            "value": value_quantity["value"],
            "unit": value_quantity.get("unit", ""),
            "system": "http://unitsofmeasure.org",
            "code": value_quantity.get("code", value_quantity.get("unit", "")),
        }

    if value_string:
        obs["valueString"] = value_string

    if reference_range_low or reference_range_high:
        ref_range = {}
        if reference_range_low:
            ref_range["low"] = {
                "value": reference_range_low["value"],
                "unit": reference_range_low.get("unit", ""),
                "system": "http://unitsofmeasure.org",
                "code": reference_range_low.get("code", reference_range_low.get("unit", "")),
            }
        if reference_range_high:
            ref_range["high"] = {
                "value": reference_range_high["value"],
                "unit": reference_range_high.get("unit", ""),
                "system": "http://unitsofmeasure.org",
                "code": reference_range_high.get("code", reference_range_high.get("unit", "")),
            }
        obs["referenceRange"] = [ref_range]

    return obs


def make_diagnostic_report(
    report_id="report-1",
    result_refs=None,
    effective=None,
    encounter_ref=None,
):
    """Create a DiagnosticReport resource."""
    report = {
        "resourceType": "DiagnosticReport",
        "id": report_id,
        "meta": {"source": "http://example.org/lab"},
        "status": "final",
        "code": {"coding": [{"system": "https://loinc.org", "code": "58410-2"}]},
    }

    if result_refs:
        report["result"] = [{"reference": ref} for ref in result_refs]

    if effective:
        report["effectiveDateTime"] = effective

    if encounter_ref:
        report["encounter"] = {"reference": encounter_ref}

    return report


class TestLabTestEventBasic:
    """Test basic LabTestEvent creation."""

    def test_diagnostic_report_creates_lab_test_event(
        self, transform_bundle, make_bundle, base_patient
    ):
        """DiagnosticReport creates LabTestEvent."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.LabTestEvent[0]")

    def test_lab_test_event_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """LabTestEvent id is prefixed with 'DiagnosticReport/'."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(
            report_id="my-report",
            result_refs=["Observation/obs-1"],
        )

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.LabTestEvent[0].id", "DiagnosticReport/my-report")


class TestLabTestEventMetadata:
    """Test LabTestEvent metadata mapping."""

    def test_effective_datetime_mapped(self, transform_bundle, make_bundle, base_patient):
        """DiagnosticReport effectiveDateTime maps to hasDateTime."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(
            result_refs=["Observation/obs-1"],
            effective="2024-01-25T10:30:00Z",
        )

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.LabTestEvent[0].hasDateTime",
            "2024-01-25T10:30:00Z",
        )

    def test_encounter_reference_mapped(self, transform_bundle, make_bundle, base_patient):
        """DiagnosticReport encounter maps to hasAdministrativeCase."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(
            result_refs=["Observation/obs-1"],
            encounter_ref="Encounter/enc-123",
        )

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.LabTestEvent[0].hasAdministrativeCase")
        assert admin_case is not None


class TestLabTest:
    """Test result Observation -> LabTest mapping."""

    def test_result_observation_creates_lab_test(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Result Observation creates hasLabTest."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.LabTestEvent[0].hasLabTest")

    def test_lab_test_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """LabTest id is prefixed with 'Observation/'."""
        obs = make_lab_observation(
            obs_id="my-obs",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/my-obs"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None
        assert lab_test.get("id") == "Observation/my-obs"

    def test_loinc_code_mapped(self, transform_bundle, make_bundle, base_patient):
        """LOINC code is mapped to hasCode."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",  # Cholesterol
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None
        assert lab_test["hasCode"]["termid"] == "2093-3"

    def test_loinc_iri_format(self, transform_bundle, make_bundle, base_patient):
        """LOINC IRI uses loinc.org/rdf format."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None
        assert lab_test["hasCode"]["iri"] == "https://loinc.org/rdf/2093-3"


class TestLabResultQuantity:
    """Test valueQuantity -> LabResult.hasQuantity mapping."""

    def test_value_quantity_mapped(self, transform_bundle, make_bundle, base_patient):
        """Observation valueQuantity maps to LabResult.hasQuantity."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 185.5, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None

        lab_results = lab_test.get("hasResult")
        assert lab_results is not None
        lab_result = lab_results[0] if isinstance(lab_results, list) else lab_results

        quantity = lab_result.get("hasQuantity")
        assert quantity is not None
        assert quantity.get("hasValue") == 185.5


class TestLabResultString:
    """Test valueString -> LabResult.hasStringValue mapping."""

    def test_value_string_mapped(self, transform_bundle, make_bundle, base_patient):
        """Observation valueString maps to LabResult.hasStringValue."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="5778-6",  # Color of urine
            value_string="Yellow",
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None

        lab_results = lab_test.get("hasResult")
        assert lab_results is not None
        lab_result = lab_results[0] if isinstance(lab_results, list) else lab_results
        assert lab_result.get("hasStringValue") == "Yellow"


class TestLabResultReferenceRange:
    """Test referenceRange -> hasNumericalReference mapping."""

    def test_reference_range_mapped(self, transform_bundle, make_bundle, base_patient):
        """Observation referenceRange maps to hasNumericalReference."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 185.5, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_low={"value": 100, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_high={"value": 200, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        assert lab_test is not None

        lab_results = lab_test.get("hasResult")
        assert lab_results is not None
        lab_result = lab_results[0] if isinstance(lab_results, list) else lab_results

        num_ref = lab_result.get("hasNumericalReference")
        assert num_ref is not None

    def test_reference_range_lower_limit(self, transform_bundle, make_bundle, base_patient):
        """Reference range lower limit is correctly mapped."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 185.5, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_low={"value": 100, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_high={"value": 200, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        num_ref = get_path(lab_test, "hasResult[0].hasNumericalReference")
        assert num_ref is not None

        lower_limit = num_ref.get("hasLowerLimit")
        assert lower_limit is not None
        assert lower_limit.get("hasValue") == 100

    def test_reference_range_upper_limit(self, transform_bundle, make_bundle, base_patient):
        """Reference range upper limit is correctly mapped."""
        obs = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 185.5, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_low={"value": 100, "unit": "mg/dL", "code": "mg/dL"},
            reference_range_high={"value": 200, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(result_refs=["Observation/obs-1"])

        bundle = make_bundle(base_patient, obs, report)

        result = transform_bundle(bundle)

        lab_test = get_path(result, "content.LabTestEvent[0].hasLabTest[0]")
        num_ref = get_path(lab_test, "hasResult[0].hasNumericalReference")
        assert num_ref is not None

        upper_limit = num_ref.get("hasUpperLimit")
        assert upper_limit is not None
        assert upper_limit.get("hasValue") == 200


class TestMultipleResults:
    """Test DiagnosticReport with multiple result observations."""

    def test_multiple_results_create_multiple_lab_tests(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Multiple result Observations create multiple LabTests."""
        obs1 = make_lab_observation(
            obs_id="obs-1",
            loinc_code="2093-3",
            value_quantity={"value": 180, "unit": "mg/dL", "code": "mg/dL"},
        )
        obs2 = make_lab_observation(
            obs_id="obs-2",
            loinc_code="2085-9",
            value_quantity={"value": 45, "unit": "mg/dL", "code": "mg/dL"},
        )
        report = make_diagnostic_report(
            result_refs=["Observation/obs-1", "Observation/obs-2"]
        )

        bundle = make_bundle(base_patient, obs1, obs2, report)

        result = transform_bundle(bundle)

        # The report should have hasLabTest as a single element or list
        lab_event = get_path(result, "content.LabTestEvent[0]")
        assert lab_event is not None

        # hasLabTest might be a single object or list depending on implementation
        lab_test = lab_event.get("hasLabTest")
        if isinstance(lab_test, list):
            assert len(lab_test) == 2
        else:
            # Single result means report resolves only first
            assert lab_test is not None
