"""
Tests for MedicationAdministrationToDrugAdministrationEvent.map

Tests the MedicationAdministration -> DrugAdministrationEvent mapping including:
- effective[x] -> hasStartDateTime/hasEndDateTime
- contained Medication -> hasDrug
- Medication.ingredient -> Drug.hasActiveIngredient (Substance)
- dosage.route -> hasAdministrationRouteCode
- dosage.dose -> Drug.hasQuantity
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_medication(
    med_id="med-1",
    gtin_code=None,
    medication_name=None,
    ingredient_cas=None,
    ingredient_snomed=None,
    ingredient_text=None,
    ingredient_quantity=None,
    form_code=None,
    form_display=None,
):
    """Create a contained Medication resource."""
    medication = {
        "resourceType": "Medication",
        "id": med_id,
    }

    codings = []
    if gtin_code:
        codings.append({
            "system": "https://wwww.gs1.org/standards/id-keys/gtin",
            "code": gtin_code,
        })

    medication["code"] = {"coding": codings}
    if medication_name:
        medication["code"]["text"] = medication_name

    if form_code:
        medication["form"] = {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-orderableDrugForm",
                    "code": form_code,
                    "display": form_display or "",
                }
            ]
        }

    ingredients = []
    if ingredient_cas or ingredient_snomed or ingredient_text:
        ingredient = {"isActive": True, "itemCodeableConcept": {"coding": []}}

        if ingredient_cas:
            ingredient["itemCodeableConcept"]["coding"].append({
                "system": "http://www.cas.org",
                "code": ingredient_cas,
            })

        if ingredient_snomed:
            ingredient["itemCodeableConcept"]["coding"].append({
                "system": "http://snomed.info/sct",
                "code": ingredient_snomed,
            })

        if ingredient_text:
            ingredient["itemCodeableConcept"]["text"] = ingredient_text

        if ingredient_quantity:
            ingredient["strength"] = {
                "extension": [
                    {
                        "url": "https://www.biomedit.ch/rdf/sphn-schema/sphn#Substance_hasQuantity",
                        "valueQuantity": {
                            "value": ingredient_quantity["value"],
                            "unit": ingredient_quantity.get("unit", "mg"),
                            "system": "http://unitsofmeasure.org",
                            "code": ingredient_quantity.get("code", "mg"),
                        },
                    }
                ]
            }

        ingredients.append(ingredient)

    if ingredients:
        medication["ingredient"] = ingredients

    return medication


def make_medication_administration(
    admin_id="medadmin-1",
    effective_datetime=None,
    effective_period=None,
    medication=None,
    route_snomed=None,
    dose_value=None,
    dose_unit=None,
    dose_system=None,
    encounter_ref=None,
):
    """Create a MedicationAdministration resource."""
    admin = {
        "resourceType": "MedicationAdministration",
        "id": admin_id,
        "meta": {"source": "http://example.org/ehr"},
        "status": "completed",
        "subject": {"reference": "Patient/pat-1"},
    }

    if medication:
        admin["contained"] = [medication]
        admin["medicationReference"] = {"reference": f"#{medication['id']}"}

    if effective_datetime:
        admin["effectiveDateTime"] = effective_datetime
    elif effective_period:
        admin["effectivePeriod"] = effective_period

    if encounter_ref:
        admin["context"] = {"reference": encounter_ref}

    dosage = {}

    if route_snomed:
        dosage["route"] = {
            "coding": [{"system": "http://snomed.info/sct", "code": route_snomed}]
        }

    if dose_value is not None:
        dosage["dose"] = {
            "value": dose_value,
            "unit": dose_unit or "mg",
            "system": dose_system or "http://unitsofmeasure.org",
            "code": dose_unit or "mg",
        }

    if dosage:
        admin["dosage"] = dosage

    return admin


class TestDrugAdministrationEventBasic:
    """Test basic DrugAdministrationEvent creation."""

    def test_medication_admin_creates_event(
        self, transform_bundle, make_bundle, base_patient
    ):
        """MedicationAdministration creates DrugAdministrationEvent."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.DrugAdministrationEvent[0]")

    def test_event_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """DrugAdministrationEvent id is prefixed with 'MedicationAdministration/'."""
        med = make_medication()
        admin = make_medication_administration(
            admin_id="my-admin",
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.DrugAdministrationEvent[0].id",
            "MedicationAdministration/my-admin",
        )


class TestEffectiveTiming:
    """Test effective[x] timing mapping."""

    def test_effective_datetime_mapped(self, transform_bundle, make_bundle, base_patient):
        """effectiveDateTime maps to hasStartDateTime."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.DrugAdministrationEvent[0].hasStartDateTime",
            "2024-01-20T10:00:00Z",
        )

    def test_effective_period_start_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """effectivePeriod.start maps to hasStartDateTime."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_period={
                "start": "2024-01-20T10:00:00Z",
                "end": "2024-01-20T10:30:00Z",
            },
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.DrugAdministrationEvent[0].hasStartDateTime",
            "2024-01-20T10:00:00Z",
        )

    def test_effective_period_end_mapped(self, transform_bundle, make_bundle, base_patient):
        """effectivePeriod.end maps to hasEndDateTime."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_period={
                "start": "2024-01-20T10:00:00Z",
                "end": "2024-01-20T10:30:00Z",
            },
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.DrugAdministrationEvent[0].hasEndDateTime",
            "2024-01-20T10:30:00Z",
        )


class TestEncounterReference:
    """Test context -> hasAdministrativeCase mapping."""

    def test_context_reference_mapped(self, transform_bundle, make_bundle, base_patient):
        """MedicationAdministration context maps to hasAdministrativeCase."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
            encounter_ref="Encounter/enc-123",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.DrugAdministrationEvent[0].hasAdministrativeCase")
        assert admin_case is not None


class TestDrug:
    """Test contained Medication -> hasDrug mapping."""

    def test_medication_creates_drug(self, transform_bundle, make_bundle, base_patient):
        """Contained Medication creates hasDrug."""
        med = make_medication(medication_name="Aspirin")
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.DrugAdministrationEvent[0].hasDrug")


class TestDrugArticle:
    """Test Medication.code -> Drug.hasArticle mapping."""

    def test_drug_article_created(self, transform_bundle, make_bundle, base_patient):
        """Medication.code creates Drug.hasArticle."""
        med = make_medication(
            gtin_code="7680123456789",
            medication_name="Aspirin 500mg",
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        assert drug is not None

        article = drug.get("hasArticle")
        assert article is not None

    def test_drug_article_gtin_code(self, transform_bundle, make_bundle, base_patient):
        """Drug article GTIN code is mapped."""
        med = make_medication(
            gtin_code="7680123456789",
            medication_name="Aspirin 500mg",
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        article = drug.get("hasArticle")
        assert article is not None

        article_code = article.get("hasCode")
        assert article_code is not None
        assert article_code.get("hasIdentifier") == "7680123456789"

    def test_drug_article_name(self, transform_bundle, make_bundle, base_patient):
        """Drug article name is mapped from code.text."""
        med = make_medication(
            gtin_code="7680123456789",
            medication_name="Aspirin 500mg",
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        article = drug.get("hasArticle")
        assert article is not None
        assert article.get("hasName") == "Aspirin 500mg"


class TestActiveIngredient:
    """Test Medication.ingredient -> Drug.hasActiveIngredient mapping."""

    def test_active_ingredient_creates_substance(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Active ingredient creates hasActiveIngredient Substance."""
        med = make_medication(
            ingredient_snomed="387458008",
            ingredient_text="Aspirin",
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        assert drug is not None

        substance = drug.get("hasActiveIngredient")
        assert substance is not None

    def test_substance_snomed_code(self, transform_bundle, make_bundle, base_patient):
        """Substance SNOMED code is mapped."""
        med = make_medication(
            ingredient_snomed="387458008",  # Aspirin
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        substances = drug.get("hasActiveIngredient")
        assert substances is not None
        substance = substances[0] if isinstance(substances, list) else substances

        code = substance.get("hasCode")
        assert code is not None
        assert code.get("termid") == "387458008"

    def test_substance_cas_code(self, transform_bundle, make_bundle, base_patient):
        """Substance CAS code is mapped."""
        med = make_medication(ingredient_cas="50-78-2")  # Aspirin CAS
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        substances = drug.get("hasActiveIngredient")
        assert substances is not None
        substance = substances[0] if isinstance(substances, list) else substances

        code = substance.get("hasCode")
        assert code is not None
        assert code.get("hasIdentifier") == "50-78-2"

    def test_substance_generic_name(self, transform_bundle, make_bundle, base_patient):
        """Substance generic name is mapped from item.text."""
        med = make_medication(
            ingredient_snomed="387458008",
            ingredient_text="Acetylsalicylic acid",
        )
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        substances = drug.get("hasActiveIngredient")
        assert substances is not None
        substance = substances[0] if isinstance(substances, list) else substances
        assert substance.get("hasGenericName") == "Acetylsalicylic acid"


class TestAdministrationRoute:
    """Test dosage.route -> hasAdministrationRouteCode mapping."""

    def test_route_snomed_mapped(self, transform_bundle, make_bundle, base_patient):
        """Route SNOMED code maps to hasAdministrationRouteCode."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
            route_snomed="26643006",  # Oral route
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.DrugAdministrationEvent[0].hasAdministrationRouteCode",
            "26643006",
            "/26643006",
        )


class TestDosage:
    """Test dosage.dose -> Drug.hasQuantity mapping."""

    def test_dose_quantity_mapped(self, transform_bundle, make_bundle, base_patient):
        """Dosage dose quantity maps to Drug.hasQuantity."""
        med = make_medication()
        admin = make_medication_administration(
            medication=med,
            effective_datetime="2024-01-20T10:00:00Z",
            dose_value=500,
            dose_unit="mg",
        )
        bundle = make_bundle(base_patient, admin)

        result = transform_bundle(bundle)

        drug = get_path(result, "content.DrugAdministrationEvent[0].hasDrug")
        assert drug is not None

        quantity = drug.get("hasQuantity")
        assert quantity is not None
        assert quantity.get("hasValue") == 500
