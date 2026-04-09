"""
Tests for ObservationFluidToFluidInputOutput.map

Covers:
- Filter: category=exam AND code in {251992000, 251840008}
- Direction → sign: intake (251992000) → positive quantity, output (251840008) → negative
- effectiveDateTime  → hasStartDateTime = hasEndDateTime
- effectivePeriod    → hasStartDateTime ≠ hasEndDateTime
- NULL valueQuantity → hasSubstance present, hasQuantity absent
- Substance SNOMED code (226465004 "Drinks", 78014005 "Urine") mapped to hasCode
- encounter.reference → hasAdministrativeCase
- meta.source        → hasSourceSystem
- Filter boundary: wrong category or wrong code → no FluidInputOutput produced
- Multiple observations in one bundle → one entry per observation
"""

from tests.helpers import (
    assert_code_mapped,
    assert_list_length,
    assert_path_equals,
    assert_path_exists,
    get_path,
)

SNOMED_SYSTEM = "http://snomed.info/sct"
FLUID_INTAKE_CODE = "251992000"   # "Fluid intake (observable entity)"
FLUID_OUTPUT_CODE = "251840008"   # "Fluid output (observable entity)"
SUBSTANCE_CODE = "105590001"      # "Substance"
DRINKS_CODE = "226465004"         # "Drinks (substance)"
URINE_CODE = "78014005"           # "Urine (substance)"


def make_fluid_observation(
    obs_id="fluid-obs-1",
    direction_code=FLUID_INTAKE_CODE,
    direction_display="Fluid intake (observable entity)",
    substance_code=DRINKS_CODE,
    substance_display="Drinks (substance)",
    value=999.0,
    unit="mL",
    effective_period=None,
    effective_datetime=None,
    encounter_ref=None,
    category_code="exam",
):
    """Create a fluid intake/output Observation."""
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "meta": {"source": "http://pukzh.ch/kisim"},
        "identifier": [{"system": "http://pukzh.ch/loop", "value": obs_id}],
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": category_code,
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": SNOMED_SYSTEM,
                    "code": direction_code,
                    "display": direction_display,
                }
            ]
        },
    }

    if encounter_ref:
        obs["encounter"] = {"reference": encounter_ref}

    if effective_period:
        obs["effectivePeriod"] = effective_period
    elif effective_datetime:
        obs["effectiveDateTime"] = effective_datetime

    if value is not None:
        obs["valueQuantity"] = {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        }

    obs["component"] = [
        {
            "code": {
                "coding": [
                    {
                        "system": SNOMED_SYSTEM,
                        "code": SUBSTANCE_CODE,
                        "display": "Substance",
                    }
                ]
            },
            "valueCodeableConcept": {
                "coding": [
                    {
                        "system": SNOMED_SYSTEM,
                        "code": substance_code,
                        "display": substance_display,
                    }
                ]
            },
        }
    ]

    return obs


class TestFluidIntake:
    """Fluid intake observations map to FluidInputOutput with positive quantity."""

    def test_intake_creates_fluid_input_output(self, transform_bundle, make_bundle, base_patient):
        """Fluid intake observation produces a FluidInputOutput entry."""
        obs = make_fluid_observation(
            direction_code=FLUID_INTAKE_CODE,
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_exists(result, "content.FluidInputOutput[0]")

    def test_intake_quantity_is_positive(self, transform_bundle, make_bundle, base_patient):
        """Intake (251992000) produces positive hasQuantity.hasValue."""
        obs = make_fluid_observation(
            direction_code=FLUID_INTAKE_CODE,
            value=999.0,
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        value = get_path(result, "content.FluidInputOutput[0].hasSubstance.hasQuantity.hasValue")
        assert value is not None
        assert value > 0
        assert value == 999.0

    def test_intake_substance_code_drinks(self, transform_bundle, make_bundle, base_patient):
        """Intake substance code 226465004 'Drinks' is mapped to hasCode."""
        obs = make_fluid_observation(
            direction_code=FLUID_INTAKE_CODE,
            substance_code=DRINKS_CODE,
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_code_mapped(
            result,
            "content.FluidInputOutput[0].hasSubstance.hasCode",
            DRINKS_CODE,
            f"/{DRINKS_CODE}",
        )

    def test_intake_unit_mapped(self, transform_bundle, make_bundle, base_patient):
        """Unit mL is mapped via UCUM concept map."""
        obs = make_fluid_observation(
            direction_code=FLUID_INTAKE_CODE,
            value=500.0,
            unit="mL",
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        unit_termid = get_path(
            result,
            "content.FluidInputOutput[0].hasSubstance.hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_termid == "mL"


class TestFluidOutput:
    """Fluid output observations map to FluidInputOutput with negative quantity."""

    def test_output_creates_fluid_input_output(self, transform_bundle, make_bundle, base_patient):
        """Fluid output observation produces a FluidInputOutput entry."""
        obs = make_fluid_observation(
            direction_code=FLUID_OUTPUT_CODE,
            substance_code=URINE_CODE,
            effective_datetime="2026-04-11T08:36:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_exists(result, "content.FluidInputOutput[0]")

    def test_output_quantity_is_negative(self, transform_bundle, make_bundle, base_patient):
        """Output (251840008) produces negative hasQuantity.hasValue."""
        obs = make_fluid_observation(
            direction_code=FLUID_OUTPUT_CODE,
            substance_code=URINE_CODE,
            value=10.0,
            effective_datetime="2026-04-11T08:36:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        value = get_path(result, "content.FluidInputOutput[0].hasSubstance.hasQuantity.hasValue")
        assert value is not None
        assert value < 0
        assert value == -10.0

    def test_output_substance_code_urine(self, transform_bundle, make_bundle, base_patient):
        """Output substance code 78014005 'Urine' is mapped to hasCode."""
        obs = make_fluid_observation(
            direction_code=FLUID_OUTPUT_CODE,
            substance_code=URINE_CODE,
            effective_datetime="2026-04-11T08:36:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_code_mapped(
            result,
            "content.FluidInputOutput[0].hasSubstance.hasCode",
            URINE_CODE,
            f"/{URINE_CODE}",
        )


class TestEffectiveDatetime:
    """effectiveDateTime and effectivePeriod both map correctly."""

    def test_effective_datetime_sets_start_and_end(self, transform_bundle, make_bundle, base_patient):
        """effectiveDateTime maps to both hasStartDateTime and hasEndDateTime."""
        obs = make_fluid_observation(
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_equals(
            result,
            "content.FluidInputOutput[0].hasStartDateTime",
            "2026-04-11T08:33:00+02:00",
        )
        assert_path_equals(
            result,
            "content.FluidInputOutput[0].hasEndDateTime",
            "2026-04-11T08:33:00+02:00",
        )

    def test_effective_period_with_different_times(self, transform_bundle, make_bundle, base_patient):
        """effectivePeriod maps start→hasStartDateTime and end→hasEndDateTime."""
        obs = make_fluid_observation(
            effective_period={
                "start": "2026-04-11T08:36:00+02:00",
                "end": "2026-04-11T08:37:00+02:00",
            },
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_equals(
            result,
            "content.FluidInputOutput[0].hasStartDateTime",
            "2026-04-11T08:36:00+02:00",
        )
        assert_path_equals(
            result,
            "content.FluidInputOutput[0].hasEndDateTime",
            "2026-04-11T08:37:00+02:00",
        )

    def test_effective_datetime_sets_equal_start_and_end(self, transform_bundle, make_bundle, base_patient):
        """effectiveDateTime maps to hasStartDateTime == hasEndDateTime (same value)."""
        obs = make_fluid_observation(
            effective_datetime="2026-04-11T09:00:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        start = get_path(result, "content.FluidInputOutput[0].hasStartDateTime")
        end = get_path(result, "content.FluidInputOutput[0].hasEndDateTime")
        assert start is not None
        assert end is not None
        assert start == end


class TestNullValue:
    """When valueQuantity is absent, hasSubstance is created without hasQuantity."""

    def test_null_value_creates_substance_without_quantity(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Absent valueQuantity → hasSubstance present, hasQuantity absent."""
        obs = make_fluid_observation(
            value=None,
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_exists(result, "content.FluidInputOutput[0].hasSubstance")
        assert get_path(result, "content.FluidInputOutput[0].hasSubstance.hasQuantity") is None


class TestEncounterReference:
    """encounter.reference maps to hasAdministrativeCase."""

    def test_with_encounter_sets_admin_case(self, transform_bundle, make_bundle, base_patient):
        """Observation with encounter reference maps hasAdministrativeCase."""
        obs = make_fluid_observation(
            effective_datetime="2026-04-11T08:33:00+02:00",
            encounter_ref="Encounter?identifier=http://pukzh.ch/loop|c7ea4a2e",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_exists(result, "content.FluidInputOutput[0].hasAdministrativeCase")

    def test_without_encounter_no_admin_case(self, transform_bundle, make_bundle, base_patient):
        """Observation without encounter reference has no hasAdministrativeCase."""
        obs = make_fluid_observation(
            effective_datetime="2026-04-11T08:33:00+02:00",
            encounter_ref=None,
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert get_path(result, "content.FluidInputOutput[0].hasAdministrativeCase") is None


class TestSourceSystem:
    """meta.source maps to hasSourceSystem."""

    def test_source_system_mapped(self, transform_bundle, make_bundle, base_patient):
        """meta.source is mapped to hasSourceSystem."""
        obs = make_fluid_observation(effective_datetime="2026-04-11T08:33:00+02:00")
        result = transform_bundle(make_bundle(base_patient, obs))

        assert_path_exists(result, "content.FluidInputOutput[0].hasSourceSystem")


class TestFilter:
    """Filter boundary: only exam category + fluid SNOMED codes are mapped."""

    def test_exam_category_with_unrelated_code_not_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """exam category + non-fluid SNOMED code → no FluidInputOutput."""
        obs = make_fluid_observation(
            direction_code="12345678",  # unrelated code
            category_code="exam",
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert get_path(result, "content.FluidInputOutput") is None

    def test_fluid_code_with_wrong_category_not_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Fluid SNOMED code + wrong category (vital-signs) → no FluidInputOutput."""
        obs = make_fluid_observation(
            direction_code=FLUID_INTAKE_CODE,
            category_code="vital-signs",  # wrong category
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, obs))

        assert get_path(result, "content.FluidInputOutput") is None


class TestMultipleObservations:
    """Multiple fluid observations produce one FluidInputOutput entry each."""

    def test_intake_and_output_produce_two_entries(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Bundle with one intake + one output → two FluidInputOutput entries."""
        intake = make_fluid_observation(
            obs_id="intake-1",
            direction_code=FLUID_INTAKE_CODE,
            substance_code=DRINKS_CODE,
            value=999.0,
            effective_datetime="2026-04-11T08:33:00+02:00",
        )
        output = make_fluid_observation(
            obs_id="output-1",
            direction_code=FLUID_OUTPUT_CODE,
            substance_code=URINE_CODE,
            value=10.0,
            effective_datetime="2026-04-11T08:36:00+02:00",
        )
        result = transform_bundle(make_bundle(base_patient, intake, output))

        assert_list_length(result, "content.FluidInputOutput", 2)

    def test_full_example_bundle_five_observations(
        self, transform_bundle, make_bundle, base_patient
    ):
        """All 5 observations from the real example produce 5 FluidInputOutput entries,
        with intake values positive and output values negative."""
        encounter_ref = "Encounter?identifier=http://pukzh.ch/loop|c7ea4a2e18c51dc8133b7b3892989ff53cbd7853851f52e68767c65624923f42"

        observations = [
            # intake, value=0.0, period
            make_fluid_observation(
                obs_id="3c47209f",
                direction_code=FLUID_INTAKE_CODE,
                substance_code=DRINKS_CODE,
                value=0.0,
                effective_period={
                    "start": "2026-04-11T08:33:00+02:00",
                    "end": "2026-04-11T08:33:00+02:00",
                },
                encounter_ref=encounter_ref,
            ),
            # intake, value=999.0, period
            make_fluid_observation(
                obs_id="d8bc95a1",
                direction_code=FLUID_INTAKE_CODE,
                substance_code=DRINKS_CODE,
                value=999.0,
                effective_period={
                    "start": "2026-04-11T08:33:00+02:00",
                    "end": "2026-04-11T08:33:00+02:00",
                },
                encounter_ref=encounter_ref,
            ),
            # output, value=10.0, period same start/end
            make_fluid_observation(
                obs_id="a1becb85",
                direction_code=FLUID_OUTPUT_CODE,
                substance_code=URINE_CODE,
                value=10.0,
                effective_period={
                    "start": "2026-04-11T08:36:00+02:00",
                    "end": "2026-04-11T08:36:00+02:00",
                },
                encounter_ref=encounter_ref,
            ),
            # output, value=11.0, period different start/end
            make_fluid_observation(
                obs_id="5e3d6a82",
                direction_code=FLUID_OUTPUT_CODE,
                substance_code=URINE_CODE,
                value=11.0,
                effective_period={
                    "start": "2026-04-11T08:36:00+02:00",
                    "end": "2026-04-11T08:37:00+02:00",
                },
                encounter_ref=encounter_ref,
            ),
            # intake, value=500.0, datetime (not period)
            make_fluid_observation(
                obs_id="d9d1e695",
                direction_code=FLUID_INTAKE_CODE,
                substance_code=DRINKS_CODE,
                value=500.0,
                effective_datetime="2026-04-11T08:33:00+02:00",
                encounter_ref=encounter_ref,
            ),
        ]
        result = transform_bundle(make_bundle(base_patient, *observations))

        assert_list_length(result, "content.FluidInputOutput", 5)

        quantities = [
            get_path(e, "hasSubstance.hasQuantity.hasValue")
            for e in get_path(result, "content.FluidInputOutput")
        ]
        positive = [v for v in quantities if v is not None and v >= 0]
        negative = [v for v in quantities if v is not None and v < 0]

        assert len(positive) == 3, f"Expected 3 intake (positive) entries, got {positive}"
        assert len(negative) == 2, f"Expected 2 output (negative) entries, got {negative}"
        assert sorted(negative) == [-11.0, -10.0]
