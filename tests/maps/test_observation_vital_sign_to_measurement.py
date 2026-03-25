"""
Tests for ObservationVitalSignToMeasurement.map

Tests the vital sign Observation -> Measurement mappings for:
- Body Temperature (bodytemp profile)
- Body Weight (bodyweight profile)
- Body Height (bodyheight profile)
- Heart Rate (heartrate profile)
- Oxygen Saturation (oxygensat profile)
- Blood Pressure (bp profile)
"""

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    assert_quantity_mapped,
    get_path,
)


def make_vital_sign(
    obs_id="obs-1",
    profile=None,
    value=None,
    unit=None,
    effective=None,
    method_code=None,
    device_type_code=None,
    encounter_ref=None,
    components=None,
    body_site_code=None,
    interpretation_code=None,
):
    """Create a vital sign Observation with specified profile."""
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
                        "code": "vital-signs",
                    }
                ]
            }
        ],
        "code": {"coding": [{"system": "http://loinc.org", "code": ""}]},
    }

    if profile:
        obs["meta"]["profile"] = [profile]

    if value is not None and unit:
        obs["valueQuantity"] = {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        }

    if effective:
        obs["effectiveDateTime"] = effective

    if method_code:
        obs["method"] = {
            "coding": [{"system": "http://snomed.info/sct", "code": method_code}]
        }

    if device_type_code:
        obs["contained"] = [
            {
                "resourceType": "Device",
                "id": "device-1",
                "type": {
                    "coding": [{"system": "http://snomed.info/sct", "code": device_type_code}]
                },
            }
        ]
        obs["device"] = {"reference": "#device-1"}

    if encounter_ref:
        obs["encounter"] = {"reference": encounter_ref}

    if components:
        obs["component"] = components

    if body_site_code:
        obs["bodySite"] = {
            "coding": [{"system": "http://snomed.info/sct", "code": body_site_code}]
        }

    if interpretation_code:
        obs["interpretation"] = [
            {"coding": [{"system": "http://snomed.info/sct", "code": interpretation_code}]}
        ]

    return obs


class TestBodyTemperature:
    """Test Body Temperature vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/bodytemp"

    def test_body_temp_creates_measurement(self, transform_bundle, make_bundle, base_patient):
        """Body temperature observation creates BodyTemperatureMeasurement."""
        obs = make_vital_sign(profile=self.PROFILE, value=37.5, unit="Cel")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BodyTemperatureMeasurement[0]")

    def test_body_temp_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Body temperature value is correctly mapped."""
        obs = make_vital_sign(profile=self.PROFILE, value=37.5, unit="Cel")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result,
            "content.BodyTemperatureMeasurement[0].hasResult[0].hasQuantity",
            37.5,
            "Cel",
        )

    def test_body_temp_effective_datetime(self, transform_bundle, make_bundle, base_patient):
        """Body temperature effectiveDateTime is mapped to hasStartDateTime."""
        obs = make_vital_sign(
            profile=self.PROFILE,
            value=37.5,
            unit="Cel",
            effective="2024-01-15T09:30:00Z",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.BodyTemperatureMeasurement[0].hasStartDateTime",
            "2024-01-15T09:30:00Z",
        )

    def test_body_temp_method_mapped(self, transform_bundle, make_bundle, base_patient):
        """Body temperature method SNOMED code is mapped."""
        obs = make_vital_sign(
            profile=self.PROFILE,
            value=37.5,
            unit="Cel",
            method_code="386725007",  # Body temperature taking
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.BodyTemperatureMeasurement[0].hasMethodCode",
            "386725007",
            "/386725007",
        )

    def test_body_temp_device_mapped(self, transform_bundle, make_bundle, base_patient):
        """Body temperature device type is mapped to hasMedicalDevice."""
        obs = make_vital_sign(
            profile=self.PROFILE,
            value=37.5,
            unit="Cel",
            device_type_code="261685002",  # Thermometer
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BodyTemperatureMeasurement[0].hasMedicalDevice")
        assert_code_mapped(
            result,
            "content.BodyTemperatureMeasurement[0].hasMedicalDevice.hasTypeCode",
            "261685002",
            "/261685002",
        )


class TestBodyWeight:
    """Test Body Weight vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/bodyweight"

    def test_body_weight_creates_measurement(self, transform_bundle, make_bundle, base_patient):
        """Body weight observation creates BodyWeightMeasurement."""
        obs = make_vital_sign(profile=self.PROFILE, value=70.5, unit="kg")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BodyWeightMeasurement[0]")

    def test_body_weight_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Body weight value is correctly mapped."""
        obs = make_vital_sign(profile=self.PROFILE, value=70.5, unit="kg")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result,
            "content.BodyWeightMeasurement[0].hasResult.hasQuantity",
            70.5,
            "kg",
        )

    def test_body_weight_encounter_reference(self, transform_bundle, make_bundle, base_patient):
        """Body weight encounter reference is mapped."""
        obs = make_vital_sign(
            profile=self.PROFILE,
            value=70.5,
            unit="kg",
            encounter_ref="Encounter/enc-123",
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.BodyWeightMeasurement[0].hasAdministrativeCase")
        assert admin_case is not None


class TestBodyHeight:
    """Test Body Height vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/bodyheight"

    def test_body_height_creates_measurement(self, transform_bundle, make_bundle, base_patient):
        """Body height observation creates BodyHeightMeasurement."""
        obs = make_vital_sign(profile=self.PROFILE, value=175.0, unit="cm")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BodyHeightMeasurement[0]")

    def test_body_height_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Body height value is correctly mapped."""
        obs = make_vital_sign(profile=self.PROFILE, value=175.0, unit="cm")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result,
            "content.BodyHeightMeasurement[0].hasResult.hasQuantity",
            175.0,
            "cm",
        )


class TestHeartRate:
    """Test Heart Rate vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/heartrate"

    def test_heart_rate_creates_measurement(self, transform_bundle, make_bundle, base_patient):
        """Heart rate observation creates HeartRateMeasurement."""
        obs = make_vital_sign(profile=self.PROFILE, value=72, unit="{beat}/min")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.HeartRateMeasurement[0]")

    def test_heart_rate_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Heart rate value is correctly mapped."""
        obs = make_vital_sign(profile=self.PROFILE, value=72, unit="{beat}/min")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result,
            "content.HeartRateMeasurement[0].hasResult[0].hasQuantity",
            72,
            "cblbeatcbrpermin",
        )

    def test_heart_rate_interpretation_regularity(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Heart rate interpretation maps to hasRegularityCode."""
        obs = make_vital_sign(
            profile=self.PROFILE,
            value=72,
            unit="{beat}/min",
            interpretation_code="271636001",  # Regular pulse
        )
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.HeartRateMeasurement[0].hasResult[0].hasRegularityCode",
            "271636001",
            "/271636001",
        )


class TestOxygenSaturation:
    """Test Oxygen Saturation vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/oxygensat"

    def test_oxygen_sat_creates_measurement(self, transform_bundle, make_bundle, base_patient):
        """Oxygen saturation observation creates OxygenSaturationMeasurement."""
        obs = make_vital_sign(profile=self.PROFILE, value=98.5, unit="%")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.OxygenSaturationMeasurement[0]")

    def test_oxygen_sat_value_mapped(self, transform_bundle, make_bundle, base_patient):
        """Oxygen saturation value is correctly mapped."""
        obs = make_vital_sign(profile=self.PROFILE, value=98.5, unit="%")
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result,
            "content.OxygenSaturationMeasurement[0].hasResult[0].hasQuantity",
            98.5,
            "percent",
        )


class TestBloodPressure:
    """Test Blood Pressure vital sign mapping."""

    PROFILE = "http://hl7.org/fhir/StructureDefinition/bp"

    def make_bp_observation(
        self,
        systolic=120,
        diastolic=80,
        mean=None,
        body_site_code=None,
    ):
        """Create a blood pressure observation with components."""
        components = [
            {
                "code": {
                    "coding": [{"system": "http://loinc.org", "code": "8480-6"}]
                },
                "valueQuantity": {
                    "value": systolic,
                    "unit": "mmHg",
                    "system": "http://unitsofmeasure.org",
                    "code": "mm[Hg]",
                },
            },
            {
                "code": {
                    "coding": [{"system": "http://loinc.org", "code": "8462-4"}]
                },
                "valueQuantity": {
                    "value": diastolic,
                    "unit": "mmHg",
                    "system": "http://unitsofmeasure.org",
                    "code": "mm[Hg]",
                },
            },
        ]

        if mean is not None:
            components.append(
                {
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "8478-0"}]
                    },
                    "valueQuantity": {
                        "value": mean,
                        "unit": "mmHg",
                        "system": "http://unitsofmeasure.org",
                        "code": "mm[Hg]",
                    },
                }
            )

        return make_vital_sign(
            profile=self.PROFILE,
            components=components,
            body_site_code=body_site_code,
        )

    def test_blood_pressure_creates_measurement(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Blood pressure observation creates BloodPressureMeasurement."""
        obs = self.make_bp_observation()
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BloodPressureMeasurement[0]")

    def test_blood_pressure_systolic_mapped(self, transform_bundle, make_bundle, base_patient):
        """Blood pressure systolic component (LOINC 8480-6) is mapped."""
        obs = self.make_bp_observation(systolic=125)
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        bp_result = get_path(result, "content.BloodPressureMeasurement[0].hasResult[0]")
        assert bp_result is not None

        systolic = get_path(bp_result, "hasSystolicPressure")
        assert systolic is not None
        assert systolic.get("hasValue") == 125

    def test_blood_pressure_diastolic_mapped(self, transform_bundle, make_bundle, base_patient):
        """Blood pressure diastolic component (LOINC 8462-4) is mapped."""
        obs = self.make_bp_observation(diastolic=82)
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        # hasResult is a list with separate entries for systolic/diastolic/mean
        bp_results = get_path(result, "content.BloodPressureMeasurement[0].hasResult")
        assert bp_results is not None

        # Find the entry that has hasDiastolicPressure
        diastolic = None
        for r in bp_results:
            if "hasDiastolicPressure" in r:
                diastolic = r["hasDiastolicPressure"]
                break
        assert diastolic is not None
        assert diastolic.get("hasValue") == 82

    def test_blood_pressure_mean_mapped(self, transform_bundle, make_bundle, base_patient):
        """Blood pressure mean component (LOINC 8478-0) is mapped if present."""
        obs = self.make_bp_observation(systolic=120, diastolic=80, mean=93)
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        # hasResult is a list with separate entries for systolic/diastolic/mean
        bp_results = get_path(result, "content.BloodPressureMeasurement[0].hasResult")
        assert bp_results is not None

        # Find the entry that has hasMeanPressure
        mean = None
        for r in bp_results:
            if "hasMeanPressure" in r:
                mean = r["hasMeanPressure"]
                break
        assert mean is not None
        assert mean.get("hasValue") == 93

    def test_blood_pressure_body_site_mapped(self, transform_bundle, make_bundle, base_patient):
        """Blood pressure bodySite is mapped to hasBodySite."""
        obs = self.make_bp_observation(body_site_code="368209003")  # Right arm
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.BloodPressureMeasurement[0].hasBodySite.hasCode",
            "368209003",
            "/368209003",
        )

    def test_blood_pressure_unit_mapped(self, transform_bundle, make_bundle, base_patient):
        """Blood pressure unit mm[Hg] is mapped to SPHN code."""
        obs = self.make_bp_observation()
        bundle = make_bundle(base_patient, obs)

        result = transform_bundle(bundle)

        systolic = get_path(
            result, "content.BloodPressureMeasurement[0].hasResult[0].hasSystolicPressure"
        )
        assert systolic is not None

        unit_code = get_path(systolic, "hasUnit.hasCode.termid")
        assert unit_code == "mmsblHgsbr"


class TestMultipleVitalSigns:
    """Test multiple vital signs in same bundle."""

    def test_different_vital_signs_mapped_separately(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Different vital sign types create their respective measurements."""
        temp = make_vital_sign(
            obs_id="temp-1",
            profile="http://hl7.org/fhir/StructureDefinition/bodytemp",
            value=37.2,
            unit="Cel",
        )
        weight = make_vital_sign(
            obs_id="weight-1",
            profile="http://hl7.org/fhir/StructureDefinition/bodyweight",
            value=72.5,
            unit="kg",
        )
        bundle = make_bundle(base_patient, temp, weight)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BodyTemperatureMeasurement[0]")
        assert_path_exists(result, "content.BodyWeightMeasurement[0]")

        temp_result = get_path(result, "content.BodyTemperatureMeasurement")
        weight_result = get_path(result, "content.BodyWeightMeasurement")

        assert len(temp_result) == 1
        assert len(weight_result) == 1
