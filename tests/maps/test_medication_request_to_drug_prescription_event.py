"""
Tests for MedicationRequestToDrugPrescriptionEvent.map -- core skeleton (no TimePattern yet).

Covers the envelope and per-instruction Drug:
- meta.source           -> hasSourceSystem
- id                    -> id (prefixed 'MedicationRequest/')
- authoredOn            -> hasDateTime (ALWAYS)
- encounter             -> hasAdministrativeCase
- one DrugPrescription per dosageInstruction, each with its OWN Drug
- contained Medication  -> Drug (article / ingredient / doseForm) via shared medication_to_drug
- doseAndRate.dose/rate -> Drug.hasQuantity (per planned administration)
- timing boundsPeriod / event -> hasStartDateTime / hasEndDateTime (mutually exclusive start)

The map is not yet wired into BundleToLoopSphn (later work), so the MedicationRequest
is transformed directly through the new map. Its target root is the SPHN Content,
so result paths start at ``DrugPrescriptionEvent[0]``.
"""

from pathlib import Path

import pytest

from tests.conftest import upload_map
from tests.helpers import get_path

MAP_URL = (
    "http://research.balgrist.ch/fhir2sphn/StructureMap/MedicationRequestToDrugPrescriptionEvent"
)
MAP_FILE = "MedicationRequestToDrugPrescriptionEvent.map"


def make_medication(
    med_id="med-1",
    gtin_code=None,
    medication_name=None,
    ingredient_snomed=None,
    ingredient_text=None,
    form_code=None,
    form_display=None,
):
    """Create a contained Medication resource."""
    medication = {"resourceType": "Medication", "id": med_id}

    codings = []
    if gtin_code:
        codings.append(
            {"system": "https://wwww.gs1.org/standards/id-keys/gtin", "code": gtin_code}
        )
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

    if ingredient_snomed or ingredient_text:
        ingredient = {"isActive": True, "itemCodeableConcept": {"coding": []}}
        if ingredient_snomed:
            ingredient["itemCodeableConcept"]["coding"].append(
                {"system": "http://snomed.info/sct", "code": ingredient_snomed}
            )
        if ingredient_text:
            ingredient["itemCodeableConcept"]["text"] = ingredient_text
        medication["ingredient"] = [ingredient]

    return medication


def _ucum_dose(value, code="mg"):
    return {"doseQuantity": {"value": value, "unit": code, "system": "http://unitsofmeasure.org", "code": code}}


def _form_dose(value, code="TAB"):
    return {
        "doseQuantity": {
            "value": value,
            "unit": code,
            "system": "http://terminology.hl7.org/CodeSystem/v3-orderableDrugForm",
            "code": code,
        }
    }


def _rate(value, code="mg/h"):
    return {"rateQuantity": {"value": value, "unit": code, "system": "http://unitsofmeasure.org", "code": code}}


def make_medication_request(
    req_id="medreq-1",
    authored_on="2024-10-15T14:18:00+02:00",
    medication=None,
    dosage_instructions=None,
    encounter_ref=None,
):
    """Create a MedicationRequest resource with one contained Medication."""
    mr = {
        "resourceType": "MedicationRequest",
        "id": req_id,
        "meta": {"source": "http://pukzh.ch/kisim"},
        "status": "active",
        "intent": "order",
        "subject": {"reference": "Patient/pat-1"},
        "authoredOn": authored_on,
    }
    if medication:
        mr["contained"] = [medication]
        mr["medicationReference"] = {"reference": f"#{medication['id']}"}
    if encounter_ref:
        mr["encounter"] = {"reference": encounter_ref}
    if dosage_instructions:
        mr["dosageInstruction"] = dosage_instructions
    return mr


@pytest.fixture(scope="module", autouse=True)
def _map_uploaded(maps_uploaded):  # noqa: ARG001
    """Ensure the (not-yet-wired) map is uploaded alongside the standard set."""
    upload_map(Path("maps") / MAP_FILE)


@pytest.fixture
def transform_request(transform_bundle):
    """Transform a MedicationRequest directly through the new map -> SPHN Content."""

    def _run(mr):
        return transform_bundle(mr, source_map=MAP_URL)

    return _run


# --------------------------------------------------------------------------- #
# Envelope
# --------------------------------------------------------------------------- #
class TestEnvelope:
    def test_event_created(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(medication_name="Aspirin"),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0]") is not None

    def test_event_id_prefixed(self, transform_request):
        mr = make_medication_request(
            req_id="my-req",
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0].id") == "MedicationRequest/my-req"

    def test_authored_on_to_has_date_time(self, transform_request):
        mr = make_medication_request(
            authored_on="2024-10-15T14:18:00+02:00",
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert (
            get_path(result, "DrugPrescriptionEvent[0].hasDateTime")
            == "2024-10-15T14:18:00+02:00"
        )

    def test_source_system_mapped(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0].hasSourceSystem") is not None

    def test_encounter_to_administrative_case(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
            encounter_ref="Encounter/enc-123",
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0].hasAdministrativeCase") is not None


# --------------------------------------------------------------------------- #
# One DrugPrescription per dosageInstruction
# --------------------------------------------------------------------------- #
class TestPrescriptionGranularity:
    def test_one_prescription_per_instruction(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {"doseAndRate": [_ucum_dose(1)]},
                {"doseAndRate": [_ucum_dose(2)]},
                {"doseAndRate": [_ucum_dose(3)]},
            ],
        )
        result = transform_request(mr)
        prescriptions = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription")
        assert isinstance(prescriptions, list) and len(prescriptions) == 3

    def test_each_prescription_has_own_drug_quantity(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {"doseAndRate": [_ucum_dose(1)]},
                {"doseAndRate": [_ucum_dose(2)]},
            ],
        )
        result = transform_request(mr)
        prescriptions = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription")
        values = sorted(p["hasDrug"]["hasQuantity"]["hasValue"] for p in prescriptions)
        assert values == [1, 2]


# --------------------------------------------------------------------------- #
# Drug (shared medication_to_drug)
# --------------------------------------------------------------------------- #
class TestDrug:
    def test_drug_created(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(medication_name="Aspirin"),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug") is not None

    def test_drug_article_gtin_and_name(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(gtin_code="7680123456789", medication_name="Aspirin 500mg"),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        article = get_path(
            result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasArticle"
        )
        assert article is not None
        assert article.get("hasName") == "Aspirin 500mg"
        assert article.get("hasCode", {}).get("hasIdentifier") == "7680123456789"

    def test_active_ingredient_snomed(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(ingredient_snomed="387458008", ingredient_text="Acetylsalicylic acid"),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        substance = get_path(
            result,
            "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasActiveIngredient",
        )
        substance = substance[0] if isinstance(substance, list) else substance
        assert substance is not None
        assert substance.get("hasCode", {}).get("termid") == "387458008"
        assert substance.get("hasGenericName") == "Acetylsalicylic acid"

    def test_dose_form_mapped(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(form_code="TAB", form_display="Tablet"),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        dose_form = get_path(
            result,
            "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasArticle.hasManufacturedDoseForm",
        )
        assert dose_form is not None
        assert dose_form.get("hasCode", {}).get("hasIdentifier") == "TAB"


# --------------------------------------------------------------------------- #
# Quantity / rate per instruction
# --------------------------------------------------------------------------- #
class TestQuantity:
    def test_ucum_dose(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(500, "mg")]}],
        )
        result = transform_request(mr)
        q = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasQuantity")
        assert q is not None
        assert q.get("hasValue") == 500
        assert q.get("hasUnit", {}).get("hasCode", {}).get("termid") == "mg"

    def test_orderable_form_dose_becomes_number(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_form_dose(2, "TAB")]}],
        )
        result = transform_request(mr)
        q = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasQuantity")
        assert q is not None
        assert q.get("hasValue") == 2
        # TAB -> UCUM {#} (cblnbcbr)
        assert q.get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbr"

    def test_rate_quantity(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_rate(1000, "mg/h")]}],
        )
        result = transform_request(mr)
        q = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug.hasQuantity")
        assert q is not None
        assert q.get("hasValue") == 1000
        assert q.get("hasUnit", {}).get("hasCode", {}).get("termid") == "mgperh"


# --------------------------------------------------------------------------- #
# Datetime branches
# --------------------------------------------------------------------------- #
class TestDateTime:
    def test_bounds_period_start_and_end(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {
                        "repeat": {
                            "boundsPeriod": {
                                "start": "2025-10-31T10:15:00+01:00",
                                "end": "2025-11-01T10:15:00+01:00",
                            }
                        }
                    },
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        assert presc.get("hasStartDateTime") == "2025-10-31T10:15:00+01:00"
        assert presc.get("hasEndDateTime") == "2025-11-01T10:15:00+01:00"

    def test_event_start_suppresses_bounds_start(self, transform_request):
        """Multiplan: event timestamp is the start; boundsPeriod.start is NOT used (no double-assign)."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(2)],
                    "timing": {
                        "event": ["2025-05-07T22:36:00+02:00"],
                        "repeat": {
                            "boundsPeriod": {
                                "start": "2025-05-07T22:36:00+02:00",
                                "end": "2025-05-08T22:36:00+02:00",
                            }
                        },
                    },
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        # start comes from event; end still from boundsPeriod
        assert presc.get("hasStartDateTime") == "2025-05-07T22:36:00+02:00"
        assert presc.get("hasEndDateTime") == "2025-05-08T22:36:00+02:00"

    def test_no_time_pattern_emitted_yet(self, transform_request):
        """WP3 does not decode timing into TimePattern."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d", "when": ["MORN"]}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        assert "hasTimePattern" not in presc
