"""
Tests for Utils.map

Tests the shared utility functions and concept maps including:
- cm-ucum-sphn: UCUM to SPHN unit mapping
- cm-comparator-sphn: Quantity comparator mapping
- quantity() function: FHIR Quantity to SPHN Quantity
- refSourceSystem() function: meta.source reference
"""

from tests.helpers import (
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_vital_sign_obs(obs_id, profile, loinc_code, value=None, unit=None, components=None):
    """Create a vital sign Observation for Utils tests."""
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "meta": {
            "source": "http://example.org/ehr",
            "profile": [profile],
        },
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                    }
                ]
            }
        ],
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc_code}]},
    }
    if value is not None and unit is not None:
        obs["valueQuantity"] = {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        }
    if components is not None:
        obs["component"] = components
    return obs


class TestUCUMMapping:
    """Test cm-ucum-sphn concept map for unit transformations."""

    def test_celsius_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM 'Cel' maps to SPHN 'Cel'."""
        obs = make_vital_sign_obs(
            "temp-1", "http://hl7.org/fhir/StructureDefinition/bodytemp", "8310-5",
            value=37.5, unit="Cel",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        unit_code = get_path(
            result,
            "content.BodyTemperatureMeasurement[0].hasResult[0].hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_code == "Cel"

    def test_kilogram_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM 'kg' maps to SPHN 'kg'."""
        obs = make_vital_sign_obs(
            "weight-1", "http://hl7.org/fhir/StructureDefinition/bodyweight", "29463-7",
            value=70.5, unit="kg",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        unit_code = get_path(
            result,
            "content.BodyWeightMeasurement[0].hasResult.hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_code == "kg"

    def test_percent_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM '%' maps to SPHN 'percent'."""
        obs = make_vital_sign_obs(
            "oxygensat-1", "http://hl7.org/fhir/StructureDefinition/oxygensat", "2708-6",
            value=98.5, unit="%",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        unit_code = get_path(
            result,
            "content.OxygenSaturationMeasurement[0].hasResult[0].hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_code == "percent"

    def test_centimeter_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM 'cm' maps to SPHN 'cm'."""
        obs = make_vital_sign_obs(
            "height-1", "http://hl7.org/fhir/StructureDefinition/bodyheight", "8302-2",
            value=175, unit="cm",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        unit_code = get_path(
            result,
            "content.BodyHeightMeasurement[0].hasResult.hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_code == "cm"

    def test_mm_hg_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM 'mm[Hg]' maps to SPHN 'mmsblHgsbr'."""
        obs = make_vital_sign_obs(
            "bp-1", "http://hl7.org/fhir/StructureDefinition/bp", "85354-9",
            components=[
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
                    "valueQuantity": {
                        "value": 120, "unit": "mmHg",
                        "system": "http://unitsofmeasure.org", "code": "mm[Hg]",
                    },
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4"}]},
                    "valueQuantity": {
                        "value": 80, "unit": "mmHg",
                        "system": "http://unitsofmeasure.org", "code": "mm[Hg]",
                    },
                },
            ],
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        # Check systolic pressure unit
        systolic = get_path(
            result, "content.BloodPressureMeasurement[0].hasResult[0].hasSystolicPressure"
        )
        assert systolic is not None

        unit_code = get_path(systolic, "hasUnit.hasCode.termid")
        assert unit_code == "mmsblHgsbr"

    def test_beat_per_min_mapped(self, transform_bundle, make_bundle, base_patient):
        """UCUM '{beat}/min' maps to SPHN 'cblbeatcbrpermin'."""
        obs = make_vital_sign_obs(
            "hr-1", "http://hl7.org/fhir/StructureDefinition/heartrate", "8867-4",
            value=72, unit="{beat}/min",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        unit_code = get_path(
            result,
            "content.HeartRateMeasurement[0].hasResult[0].hasQuantity.hasUnit.hasCode.termid",
        )
        assert unit_code == "cblbeatcbrpermin"


class TestQuantityValue:
    """Test quantity value mapping."""

    def test_integer_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Integer quantity value is correctly mapped."""
        obs = make_vital_sign_obs(
            "weight-1", "http://hl7.org/fhir/StructureDefinition/bodyweight", "29463-7",
            value=70, unit="kg",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        value = get_path(
            result,
            "content.BodyWeightMeasurement[0].hasResult.hasQuantity.hasValue",
        )
        assert value == 70

    def test_decimal_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Decimal quantity value is correctly mapped."""
        obs = make_vital_sign_obs(
            "temp-1", "http://hl7.org/fhir/StructureDefinition/bodytemp", "8310-5",
            value=37.55, unit="Cel",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        value = get_path(
            result,
            "content.BodyTemperatureMeasurement[0].hasResult[0].hasQuantity.hasValue",
        )
        assert value == 37.55


class TestSourceSystemReference:
    """Test refSourceSystem function."""

    def test_source_system_referenced(self, transform_bundle, make_bundle, base_patient):
        """Resources reference their source system."""
        base_patient["meta"]["source"] = "http://example.org/hospital-ehr"
        base_patient["birthDate"] = "1990-01-01"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        # Check that source system is created
        source_systems = get_path(result, "content.SourceSystem")
        assert source_systems is not None
        assert len(source_systems) >= 1

        # Check that Birth references the source system
        birth = get_path(result, "content.Birth[0]")
        assert birth is not None
        assert birth.get("hasSourceSystem") is not None

    def test_multiple_source_systems_deduplicated(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Multiple resources from same source create only one SourceSystem."""
        base_patient["meta"]["source"] = "http://example.org/ehr"
        base_patient["gender"] = "male"
        base_patient["birthDate"] = "1990-01-01"

        obs = make_vital_sign_obs(
            "temp-1", "http://hl7.org/fhir/StructureDefinition/bodytemp", "8310-5",
            value=37.5, unit="Cel",
        )

        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        source_systems = get_path(result, "content.SourceSystem")
        assert source_systems is not None

        # Should have only one SourceSystem with this ID
        matching = [ss for ss in source_systems if ss.get("id") == "http://example.org/ehr"]
        assert len(matching) == 1
