"""
Tests for AllergyIntoleranceToAllergy.map

Tests the AllergyIntolerance -> Allergy mapping including:
- code -> hasAllergen (SNOMED CT codes)
- recordedDate -> hasFirstRecordDateTime
"""

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_allergy_intolerance(
    allergy_id="allergy-1",
    snomed_code=None,
    recorded_date=None,
):
    """Create an AllergyIntolerance resource."""
    allergy = {
        "resourceType": "AllergyIntolerance",
        "id": allergy_id,
        "meta": {"source": "http://example.org/ehr"},
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                    "code": "active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                    "code": "confirmed",
                }
            ]
        },
        "patient": {"reference": "Patient/pat-1"},
    }

    if snomed_code:
        allergy["code"] = {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]
        }

    if recorded_date:
        allergy["recordedDate"] = recorded_date

    return allergy


class TestAllergyBasic:
    """Test basic Allergy creation."""

    def test_allergy_intolerance_creates_allergy(
        self, transform_bundle, make_bundle, base_patient
    ):
        """AllergyIntolerance creates Allergy."""
        allergy = make_allergy_intolerance(snomed_code="91935009")
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Allergy[0]")

    def test_allergy_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """Allergy id is prefixed with 'AllergyIntolerance/'."""
        allergy = make_allergy_intolerance(allergy_id="my-allergy", snomed_code="91935009")
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.Allergy[0].id", "AllergyIntolerance/my-allergy")


class TestAllergen:
    """Test AllergyIntolerance.code -> Allergy.hasAllergen mapping."""

    def test_snomed_code_maps_to_allergen(self, transform_bundle, make_bundle, base_patient):
        """SNOMED CT code maps to hasAllergen with correct code."""
        allergy = make_allergy_intolerance(snomed_code="91935009")  # Penicillin allergy
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Allergy[0].hasAllergen")
        assert_code_mapped(
            result,
            "content.Allergy[0].hasAllergen.hasCode[0]",
            "91935009",
            "/91935009",
        )

    def test_allergen_iri_format(self, transform_bundle, make_bundle, base_patient):
        """Allergen IRI uses snomed.info/id format."""
        allergy = make_allergy_intolerance(snomed_code="300913006")  # Peanut allergy
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        allergen_iri = get_path(result, "content.Allergy[0].hasAllergen.hasCode[0].iri")
        assert allergen_iri == "http://snomed.info/id/300913006"


class TestRecordedDate:
    """Test recordedDate -> hasFirstRecordDateTime mapping."""

    def test_recorded_date_mapped(self, transform_bundle, make_bundle, base_patient):
        """AllergyIntolerance recordedDate maps to hasFirstRecordDateTime."""
        allergy = make_allergy_intolerance(
            snomed_code="91935009",
            recorded_date="2024-01-10T14:30:00Z",
        )
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.Allergy[0].hasFirstRecordDateTime",
            "2024-01-10T14:30:00Z",
        )

    def test_no_recorded_date_no_datetime(self, transform_bundle, make_bundle, base_patient):
        """Allergy without recordedDate has no hasFirstRecordDateTime."""
        allergy = make_allergy_intolerance(snomed_code="91935009")
        bundle = make_bundle(base_patient, allergy)

        result = transform_bundle(bundle)

        datetime = get_path(result, "content.Allergy[0].hasFirstRecordDateTime")
        assert datetime is None


class TestMultipleAllergies:
    """Test multiple allergies in bundle."""

    def test_multiple_allergies_mapped(self, transform_bundle, make_bundle, base_patient):
        """Multiple AllergyIntolerance resources create multiple Allergies."""
        allergy1 = make_allergy_intolerance(
            allergy_id="allergy-1",
            snomed_code="91935009",
        )
        allergy2 = make_allergy_intolerance(
            allergy_id="allergy-2",
            snomed_code="300913006",
        )
        bundle = make_bundle(base_patient, allergy1, allergy2)

        result = transform_bundle(bundle)

        allergies = get_path(result, "content.Allergy")
        assert allergies is not None
        assert len(allergies) == 2

        ids = [a.get("id") for a in allergies]
        assert "AllergyIntolerance/allergy-1" in ids
        assert "AllergyIntolerance/allergy-2" in ids
