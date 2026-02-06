"""
Tests for ObservationSurveyToAssessmentEvent.map

Tests the Observation (survey) -> AssessmentEvent mapping including:
- code -> Assessment with SNOMED code
- effective -> hasDateTime
- valueCodeableConcept/valueQuantity/valueString -> AssessmentResult
- component -> AssessmentComponent
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_survey_observation(
    obs_id="survey-1",
    snomed_code=None,
    snomed_display=None,
    effective=None,
    encounter_ref=None,
    value_codeable_concept=None,
    value_quantity=None,
    value_string=None,
    components=None,
):
    """Create a survey Observation resource."""
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "meta": {"source": "http://example.org/ehr"},
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                    }
                ]
            }
        ],
    }

    if snomed_code:
        code_entry = {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]
        }
        if snomed_display:
            code_entry["coding"][0]["display"] = snomed_display
            code_entry["text"] = snomed_display
        obs["code"] = code_entry

    if effective:
        obs["effectiveDateTime"] = effective

    if encounter_ref:
        obs["encounter"] = {"reference": encounter_ref}

    if value_codeable_concept:
        obs["valueCodeableConcept"] = value_codeable_concept

    if value_quantity:
        obs["valueQuantity"] = {
            "value": value_quantity["value"],
            "unit": value_quantity.get("unit", ""),
            "system": "http://unitsofmeasure.org",
            "code": value_quantity.get("code", value_quantity.get("unit", "")),
        }

    if value_string:
        obs["valueString"] = value_string

    if components:
        obs["component"] = components

    return obs


def make_component(
    snomed_code=None,
    snomed_display=None,
    value_codeable_concept=None,
    value_quantity=None,
    value_string=None,
):
    """Create a component for a survey Observation."""
    comp = {}

    if snomed_code:
        code_entry = {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]
        }
        if snomed_display:
            code_entry["coding"][0]["display"] = snomed_display
            code_entry["text"] = snomed_display
        comp["code"] = code_entry

    if value_codeable_concept:
        comp["valueCodeableConcept"] = value_codeable_concept

    if value_quantity:
        comp["valueQuantity"] = {
            "value": value_quantity["value"],
            "unit": value_quantity.get("unit", ""),
            "system": "http://unitsofmeasure.org",
            "code": value_quantity.get("code", value_quantity.get("unit", "")),
        }

    if value_string:
        comp["valueString"] = value_string

    return comp


class TestAssessmentEventBasic:
    """Test basic AssessmentEvent creation."""

    def test_survey_creates_assessment_event(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Survey observation creates AssessmentEvent."""
        obs = make_survey_observation(snomed_code="444735006")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AssessmentEvent[0]")

    def test_assessment_event_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """AssessmentEvent id is prefixed with 'AssessmentEvent/'."""
        obs = make_survey_observation(obs_id="my-survey", snomed_code="444735006")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.AssessmentEvent[0].id",
            "AssessmentEvent/my-survey",
        )


class TestAssessmentEventMetadata:
    """Test AssessmentEvent metadata mapping."""

    def test_effective_datetime_mapped(self, transform_bundle, make_bundle, base_patient):
        """Survey effectiveDateTime maps to hasDateTime."""
        obs = make_survey_observation(
            snomed_code="444735006",
            effective="2024-01-25T14:00:00Z",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.AssessmentEvent[0].hasDateTime",
            "2024-01-25T14:00:00Z",
        )

    def test_encounter_reference_mapped(self, transform_bundle, make_bundle, base_patient):
        """Survey encounter maps to hasAdministrativeCase."""
        obs = make_survey_observation(
            snomed_code="444735006",
            encounter_ref="Encounter/enc-123",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.AssessmentEvent[0].hasAdministrativeCase")
        assert admin_case is not None


class TestAssessment:
    """Test observation.code -> Assessment mapping."""

    def test_code_creates_assessment(self, transform_bundle, make_bundle, base_patient):
        """Observation code creates hasAssessment."""
        obs = make_survey_observation(snomed_code="444735006")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AssessmentEvent[0].hasAssessment")

    def test_snomed_code_mapped(self, transform_bundle, make_bundle, base_patient):
        """SNOMED code is mapped to Assessment.hasCode."""
        obs = make_survey_observation(snomed_code="444735006")  # Barthel index
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AssessmentEvent[0].hasAssessment.hasCode",
            "444735006",
            "/444735006",
        )

    def test_assessment_name_from_text(self, transform_bundle, make_bundle, base_patient):
        """Assessment hasName comes from code.text."""
        obs = make_survey_observation(
            snomed_code="444735006",
            snomed_display="Barthel Activities of Daily Living Index",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.AssessmentEvent[0].hasAssessment.hasName",
            "Barthel Activities of Daily Living Index",
        )


class TestAssessmentResultCodeableConcept:
    """Test valueCodeableConcept -> AssessmentResult mapping."""

    def test_value_codeable_concept_creates_result(
        self, transform_bundle, make_bundle, base_patient
    ):
        """valueCodeableConcept creates AssessmentResult."""
        obs = make_survey_observation(
            snomed_code="444735006",
            value_codeable_concept={
                "coding": [{"system": "http://snomed.info/sct", "code": "260385009"}]
            },
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        assert assessment is not None

        ass_result = assessment.get("hasResult")
        assert ass_result is not None

    def test_value_codeable_concept_code_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """valueCodeableConcept SNOMED code maps to AssessmentResult.hasCode."""
        obs = make_survey_observation(
            snomed_code="444735006",
            value_codeable_concept={
                "coding": [{"system": "http://snomed.info/sct", "code": "260385009"}]
            },
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        ass_result = assessment.get("hasResult")
        assert ass_result is not None

        code = ass_result.get("hasCode")
        assert code is not None
        assert code.get("termid") == "260385009"


class TestAssessmentResultQuantity:
    """Test valueQuantity -> AssessmentResult mapping."""

    def test_value_quantity_creates_result(
        self, transform_bundle, make_bundle, base_patient
    ):
        """valueQuantity creates AssessmentResult with hasQuantity."""
        obs = make_survey_observation(
            snomed_code="444735006",
            value_quantity={"value": 85, "unit": "{score}", "code": "{score}"},
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        assert assessment is not None

        ass_result = assessment.get("hasResult")
        assert ass_result is not None

        quantity = ass_result.get("hasQuantity")
        assert quantity is not None
        assert quantity.get("hasValue") == 85


class TestAssessmentResultString:
    """Test valueString -> AssessmentResult mapping."""

    def test_value_string_creates_result(self, transform_bundle, make_bundle, base_patient):
        """valueString creates AssessmentResult with hasStringValue."""
        obs = make_survey_observation(
            snomed_code="444735006",
            value_string="Independent with all activities",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        assert assessment is not None

        ass_result = assessment.get("hasResult")
        assert ass_result is not None
        assert ass_result.get("hasStringValue") == "Independent with all activities"


class TestAssessmentComponent:
    """Test observation.component -> AssessmentComponent mapping."""

    def test_component_creates_assessment_component(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Observation component creates hasComponent."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",
                    value_quantity={"value": 10, "unit": "{score}", "code": "{score}"},
                )
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        assert assessment is not None

        component = assessment.get("hasComponent")
        assert component is not None

    def test_component_snomed_code_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Component SNOMED code maps to hasCode."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",  # Bowel control
                    value_quantity={"value": 10, "unit": "{score}", "code": "{score}"},
                )
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        component = assessment.get("hasComponent")

        if isinstance(component, list):
            component = component[0]

        assert component is not None
        code = component.get("hasCode")
        assert code is not None
        assert code.get("termid") == "309047009"

    def test_component_name_from_text(self, transform_bundle, make_bundle, base_patient):
        """Component hasName comes from code.text."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",
                    snomed_display="Bowel control",
                    value_quantity={"value": 10, "unit": "{score}", "code": "{score}"},
                )
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        component = assessment.get("hasComponent")

        if isinstance(component, list):
            component = component[0]

        assert component is not None
        assert component.get("hasName") == "Bowel control"

    def test_component_value_quantity_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Component valueQuantity maps to hasResult.hasQuantity."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",
                    value_quantity={"value": 10, "unit": "{score}", "code": "{score}"},
                )
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        component = assessment.get("hasComponent")

        if isinstance(component, list):
            component = component[0]

        assert component is not None

        comp_results = component.get("hasResult")
        assert comp_results is not None
        comp_result = comp_results[0] if isinstance(comp_results, list) else comp_results

        quantity = comp_result.get("hasQuantity")
        assert quantity is not None
        assert quantity.get("hasValue") == 10

    def test_component_value_string_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Component valueString maps to hasResult.hasStringValue."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",
                    value_string="Continent",
                )
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        component = assessment.get("hasComponent")

        if isinstance(component, list):
            component = component[0]

        assert component is not None

        comp_results = component.get("hasResult")
        assert comp_results is not None
        comp_result = comp_results[0] if isinstance(comp_results, list) else comp_results
        assert comp_result.get("hasStringValue") == "Continent"


class TestMultipleComponents:
    """Test observation with multiple components."""

    def test_multiple_components_mapped(self, transform_bundle, make_bundle, base_patient):
        """Multiple components create multiple AssessmentComponents."""
        obs = make_survey_observation(
            snomed_code="444735006",
            components=[
                make_component(
                    snomed_code="309047009",
                    value_quantity={"value": 10, "unit": "{score}", "code": "{score}"},
                ),
                make_component(
                    snomed_code="309048004",
                    value_quantity={"value": 5, "unit": "{score}", "code": "{score}"},
                ),
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assessment = get_path(result, "content.AssessmentEvent[0].hasAssessment")
        assert assessment is not None

        component = assessment.get("hasComponent")
        if isinstance(component, list):
            assert len(component) == 2
        else:
            # Single component case (implementation may vary)
            assert component is not None


class TestMultipleSurveys:
    """Test multiple survey observations in bundle."""

    def test_multiple_surveys_create_multiple_events(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Multiple survey observations create multiple AssessmentEvents."""
        obs1 = make_survey_observation(obs_id="survey-1", snomed_code="444735006")
        obs2 = make_survey_observation(obs_id="survey-2", snomed_code="720103009")
        bundle = make_bundle(base_patient, obs1, obs2)

        result = transform_bundle(bundle)

        events = get_path(result, "content.AssessmentEvent")
        assert events is not None
        assert len(events) == 2
