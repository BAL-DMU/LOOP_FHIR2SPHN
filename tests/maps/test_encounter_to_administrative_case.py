"""
Tests for EncounterToAdministrativeCase.map

Tests the Encounter -> AdministrativeCase mapping including:
- period.start/end -> Admission/Discharge
- class -> CareHandling
- type [304903009 day care] -> CareHandling (overrides class)
- hospitalization.admitSource -> Admission.hasOriginLocation
- hospitalization.extension[dischargedestination] -> Discharge.hasTargetLocation
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_encounter(
    encounter_id="enc-1",
    start=None,
    end=None,
    class_code=None,
    type_codes=None,
    admit_source=None,
    discharge_destination=None,
):
    """Create an Encounter resource with optional fields."""
    encounter = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "meta": {"source": "http://example.org/ehr"},
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
    }

    if class_code:
        encounter["class"]["code"] = class_code

    if type_codes:
        encounter["type"] = [
            {"coding": [{"system": "http://snomed.info/sct", "code": code}]}
            for code in type_codes
        ]

    if start or end:
        encounter["period"] = {}
        if start:
            encounter["period"]["start"] = start
        if end:
            encounter["period"]["end"] = end

    hospitalization = {}

    if admit_source:
        hospitalization["admitSource"] = {
            "coding": [
                {
                    "system": "http://fhir.ch/ig/ch-core/CodeSystem/bfs-medstats-17-admitsource",
                    "code": admit_source,
                }
            ]
        }

    if discharge_destination:
        hospitalization["extension"] = [
            {
                "url": "http://fhir.ch/ig/ch-core/StructureDefinition/ch-ext-bfs-ms-dischargedestination",
                "valueCoding": {
                    "system": "http://fhir.ch/ig/ch-core/CodeSystem/bfs-medstats-28-dischargedestination",
                    "code": discharge_destination,
                },
            }
        ]

    if hospitalization:
        encounter["hospitalization"] = hospitalization

    return encounter


class TestAdministrativeCaseBasic:
    """Test basic AdministrativeCase creation."""

    def test_encounter_creates_administrative_case(self, transform_bundle, make_bundle, base_patient):
        """Encounter creates AdministrativeCase."""
        encounter = make_encounter()
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AdministrativeCase[0]")

    def test_administrative_case_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """AdministrativeCase id is prefixed with 'Encounter/'."""
        encounter = make_encounter(encounter_id="my-encounter")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.AdministrativeCase[0].id", "Encounter/my-encounter")


class TestAdmission:
    """Test period.start -> Admission mapping."""

    def test_period_start_creates_admission(self, transform_bundle, make_bundle, base_patient):
        """Encounter period.start creates Admission with datetime."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AdministrativeCase[0].hasAdmission")
        assert_path_equals(
            result,
            "content.AdministrativeCase[0].hasAdmission.hasDateTime",
            "2024-01-15T08:00:00Z",
        )

    def test_admit_source_1_maps_home(self, transform_bundle, make_bundle, base_patient):
        """admitSource code 1 (Zuhause) maps to SNOMED 264362003."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z", admit_source="1")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasAdmission.hasOriginLocation.hasTypeCode",
            "264362003",
            "/264362003",
        )

    def test_admit_source_3_maps_nursing_home(self, transform_bundle, make_bundle, base_patient):
        """admitSource code 3 (Pflegeheim) maps to SNOMED 42665001."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z", admit_source="3")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasAdmission.hasOriginLocation.hasTypeCode",
            "42665001",
            "/42665001",
        )

    def test_admit_source_5_maps_psychiatric(self, transform_bundle, make_bundle, base_patient):
        """admitSource code 5 (Psychiatrische Klinik) maps to SNOMED 702914003."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z", admit_source="5")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasAdmission.hasOriginLocation.hasTypeCode",
            "702914003",
            "/702914003",
        )

    def test_admit_source_6_maps_acute_hospital(self, transform_bundle, make_bundle, base_patient):
        """admitSource code 6 (Akutspital) maps to SNOMED 25731000087105."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z", admit_source="6")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasAdmission.hasOriginLocation.hasTypeCode",
            "25731000087105",
            "/25731000087105",
        )


class TestDischarge:
    """Test period.end -> Discharge mapping."""

    def test_period_end_creates_discharge(self, transform_bundle, make_bundle, base_patient):
        """Encounter period.end creates Discharge with datetime."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z", end="2024-01-20T14:00:00Z")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AdministrativeCase[0].hasDischarge")
        assert_path_equals(
            result,
            "content.AdministrativeCase[0].hasDischarge.hasDateTime",
            "2024-01-20T14:00:00Z",
        )

    def test_no_period_end_no_discharge(self, transform_bundle, make_bundle, base_patient):
        """Encounter without period.end has no Discharge."""
        encounter = make_encounter(start="2024-01-15T08:00:00Z")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        discharge = get_path(result, "content.AdministrativeCase[0].hasDischarge")
        assert discharge is None

    def test_discharge_destination_1_maps_home(self, transform_bundle, make_bundle, base_patient):
        """dischargeDestination code 1 (Zuhause) maps to SNOMED 264362003."""
        encounter = make_encounter(
            start="2024-01-15T08:00:00Z",
            end="2024-01-20T14:00:00Z",
            discharge_destination="1",
        )
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasDischarge.hasTargetLocation.hasTypeCode",
            "264362003",
            "/264362003",
        )

    def test_discharge_destination_2_maps_nursing_home(
        self, transform_bundle, make_bundle, base_patient
    ):
        """dischargeDestination code 2 (Pflegeheim) maps to SNOMED 42665001."""
        encounter = make_encounter(
            start="2024-01-15T08:00:00Z",
            end="2024-01-20T14:00:00Z",
            discharge_destination="2",
        )
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasDischarge.hasTargetLocation.hasTypeCode",
            "42665001",
            "/42665001",
        )

    def test_discharge_destination_5_maps_rehab(self, transform_bundle, make_bundle, base_patient):
        """dischargeDestination code 5 (Rehabilitationsklinik) maps to SNOMED 702916001."""
        encounter = make_encounter(
            start="2024-01-15T08:00:00Z",
            end="2024-01-20T14:00:00Z",
            discharge_destination="5",
        )
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasDischarge.hasTargetLocation.hasTypeCode",
            "702916001",
            "/702916001",
        )


class TestCareHandling:
    """Test class -> CareHandling mapping."""

    def test_class_imp_maps_inpatient(self, transform_bundle, make_bundle, base_patient):
        """Encounter class IMP (inpatient) maps to SNOMED 394656005."""
        encounter = make_encounter(class_code="IMP")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.AdministrativeCase[0].hasCareHandling")
        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            "394656005",
            "/394656005",
        )

    def test_class_amb_maps_outpatient(self, transform_bundle, make_bundle, base_patient):
        """Encounter class AMB (ambulatory) maps to SNOMED 371883000."""
        encounter = make_encounter(class_code="AMB")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            "371883000",
            "/371883000",
        )


class TestCareHandlingDayCare:
    """Test type [304903009 day care] -> CareHandling, overriding the class-derived code.

    KISIM FALLART 'T' (teilstationaer) has no v3-ActCode equivalent, so the FHIR extraction
    emits class = IMP plus Encounter.type = SNOMED 304903009. The SPHN code must come from
    the type, not from the class.
    """

    DAY_CARE = "304903009"
    INPATIENT = "394656005"

    def test_class_imp_without_type_is_not_day_care(
        self, transform_bundle, make_bundle, base_patient
    ):
        """class IMP alone (no type) stays Inpatient - no day care leaks in."""
        encounter = make_encounter(class_code="IMP")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            self.INPATIENT,
            f"/{self.INPATIENT}",
        )

    def test_class_amb_without_type_is_not_day_care(
        self, transform_bundle, make_bundle, base_patient
    ):
        """class AMB alone (no type) stays Outpatient - no day care leaks in."""
        encounter = make_encounter(class_code="AMB")
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        termid = get_path(
            result, "content.AdministrativeCase[0].hasCareHandling.hasTypeCode.termid"
        )
        assert termid != self.DAY_CARE, f"unexpected day care code for class AMB: {termid!r}"
        assert termid == "371883000"

    def test_type_day_care_maps_day_care(self, transform_bundle, make_bundle, base_patient):
        """class IMP + type 304903009 maps to SNOMED 304903009, not 394656005."""
        encounter = make_encounter(class_code="IMP", type_codes=[self.DAY_CARE])
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            self.DAY_CARE,
            f"/{self.DAY_CARE}",
        )

    def test_class_amb_with_day_care_type_maps_day_care(
        self, transform_bundle, make_bundle, base_patient
    ):
        """The type override is independent of the class value: AMB + day care is day care.

        Not reachable from the KISIM extraction (FALLART 'T' always emits IMP), but type is the
        more specific statement, so it wins over any class.
        """
        encounter = make_encounter(class_code="AMB", type_codes=[self.DAY_CARE])
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            self.DAY_CARE,
            f"/{self.DAY_CARE}",
        )

    def test_type_day_care_yields_single_type_code(
        self, transform_bundle, make_bundle, base_patient
    ):
        """hasTypeCode is 1..1: the day care code replaces the class code, it is not added."""
        encounter = make_encounter(class_code="IMP", type_codes=[self.DAY_CARE])
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        type_code = get_path(result, "content.AdministrativeCase[0].hasCareHandling.hasTypeCode")
        assert not isinstance(type_code, list), (
            f"hasTypeCode must be a single Code, got a list: {type_code!r}"
        )
        assert type_code["termid"] == self.DAY_CARE

    def test_unrelated_type_falls_back_to_class(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A SNOMED type other than 304903009 does not override the class-derived code."""
        encounter = make_encounter(class_code="IMP", type_codes=["11429006"])  # Consultation

        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            self.INPATIENT,
            f"/{self.INPATIENT}",
        )

    def test_day_care_among_several_types_still_wins(
        self, transform_bundle, make_bundle, base_patient
    ):
        """The day care code is found even when Encounter.type carries other codings too."""
        encounter = make_encounter(class_code="IMP", type_codes=["11429006", self.DAY_CARE])
        bundle = make_bundle(base_patient, encounter)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeCase[0].hasCareHandling.hasTypeCode",
            self.DAY_CARE,
            f"/{self.DAY_CARE}",
        )


class TestMultipleEncounters:
    """Test multiple encounters in bundle."""

    def test_multiple_encounters_create_multiple_cases(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Multiple encounters create multiple AdministrativeCases."""
        enc1 = make_encounter(encounter_id="enc-1", start="2024-01-15T08:00:00Z")
        enc2 = make_encounter(encounter_id="enc-2", start="2024-02-01T10:00:00Z")
        bundle = make_bundle(base_patient, enc1, enc2)

        result = transform_bundle(bundle)

        cases = get_path(result, "content.AdministrativeCase")
        assert cases is not None
        assert len(cases) == 2

        case_ids = [c.get("id") for c in cases]
        assert "Encounter/enc-1" in case_ids
        assert "Encounter/enc-2" in case_ids
