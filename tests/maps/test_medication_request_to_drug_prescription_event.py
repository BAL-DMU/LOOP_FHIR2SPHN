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
# Required-attribute guards (SPHN cardinalities stricter than FHIR)
# --------------------------------------------------------------------------- #
class TestRequiredAttributeGuards:
    """SPHN requires DrugPrescriptionEvent.hasDateTime (1..1), .hasDrugPrescription
    (1..*) and each DrugPrescription.hasDrug (1..1). FHIR MedicationRequest is
    looser, so the event is suppressed entirely when the source of any required
    attribute is missing (rather than emitting a structurally invalid event)."""

    def test_missing_authored_on_suppresses_event(self, transform_request):
        # authoredOn -> hasDateTime (1..1)
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        del mr["authoredOn"]
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent") is None

    def test_missing_dosage_instruction_suppresses_event(self, transform_request):
        # dosageInstruction -> hasDrugPrescription (1..*)
        mr = make_medication_request(medication=make_medication())
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent") is None

    def test_missing_contained_medication_suppresses_event(self, transform_request):
        # contained Medication -> hasDrugPrescription.hasDrug (1..1)
        mr = make_medication_request(
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent") is None

    def test_all_required_present_emits_event(self, transform_request):
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)]}],
        )
        result = transform_request(mr)
        assert get_path(result, "DrugPrescriptionEvent[0]") is not None
        assert (
            get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0].hasDrug")
            is not None
        )


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

    def test_single_event_sets_start_and_end(self, transform_request):
        """Once/Multiplan: a single point-in-time event sets BOTH start and end (no boundsPeriod)."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(2)],
                    "timing": {
                        "event": ["2025-05-07T22:36:00+02:00"],
                    },
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        # a single event is the whole window: start == end == event
        assert presc.get("hasStartDateTime") == "2025-05-07T22:36:00+02:00"
        assert presc.get("hasEndDateTime") == "2025-05-07T22:36:00+02:00"

    def test_once_emits_no_time_pattern(self, transform_request):
        """Pattern A (Once): single timing.event -> start == end == event, no TimePattern."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "asNeededBoolean": False,
                    "timing": {
                        "event": ["2024-10-15T14:18:00+02:00"],
                    },
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        assert presc.get("hasStartDateTime") == "2024-10-15T14:18:00+02:00"
        assert presc.get("hasEndDateTime") == "2024-10-15T14:18:00+02:00"
        assert "hasTimePattern" not in presc


# --------------------------------------------------------------------------- #
# TimePattern -- simple shapes A, B, C, J, K
# --------------------------------------------------------------------------- #
def _time_patterns(presc):
    """Return TimePattern(s) of a prescription as a list (or [] if none)."""
    tp = (presc or {}).get("hasTimePattern")
    if tp is None:
        return []
    return tp if isinstance(tp, list) else [tp]


def _tod(tp):
    return (tp.get("hasTimeOfDayCode") or {}).get("termid")


def _freq(tp):
    return tp.get("hasFrequency")


def _type(tp):
    return (tp.get("hasTypeCode") or {}).get("termid")


def _offset(tp):
    return tp.get("hasOffset")


class TestTimePatternDaily:
    def test_b_schema_when_one_tp_per_when(self, transform_request):
        """B: when=[MORN,EVE] -> two TimePatterns, freq 1 {#}/d, ToD Morning/Evening."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d", "when": ["MORN", "EVE"]}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        tps = _time_patterns(presc)
        assert len(tps) == 2
        tods = sorted(_tod(tp) for tp in tps)
        assert tods == ["3157002", "73775008"]  # Evening, Morning
        for tp in tps:
            f = _freq(tp)
            assert f is not None and f.get("hasValue") == 1
            assert f.get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperd"

    def test_c_schedule_canonical_and_offgrid(self, transform_request):
        """C: timeOfDay=[08:00:00, 09:15:00], no when -> two TPs; only the canonical one is coded."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(2)],
                    "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d", "timeOfDay": ["08:00:00", "09:15:00"]}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        tps = _time_patterns(presc)
        assert len(tps) == 2
        # every TP carries the daily frequency
        for tp in tps:
            assert _freq(tp).get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperd"
        coded = sorted(t for t in (_tod(tp) for tp in tps) if t is not None)
        assert coded == ["73775008"]  # 08:00 -> Morning; 09:15 off-grid -> no code

    def test_k_bare_daily_single_tp_no_tod(self, transform_request):
        """K: period=1, periodUnit=d, no when/timeOfDay -> single TP, freq 1 {#}/d, no ToD."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d"}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        tps = _time_patterns(presc)
        assert len(tps) == 1
        tp = tps[0]
        assert _freq(tp).get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperd"
        assert "hasTimeOfDayCode" not in tp

    def test_b_does_not_set_type_code(self, transform_request):
        """Daily shapes carry frequency/ToD only -- no hasTypeCode (relaxed to 0..1 in WP1)."""
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
        tp = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))[0]
        assert "hasTypeCode" not in tp


class TestTimePatternMultiplan:
    def test_j_event_no_time_pattern(self, transform_request):
        """J: single timing.event -> start == end == event, NO TimePattern."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(2)],
                    "timing": {
                        "event": ["2025-05-07T22:36:00+02:00"],
                    },
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        assert presc.get("hasStartDateTime") == "2025-05-07T22:36:00+02:00"
        assert presc.get("hasEndDateTime") == "2025-05-07T22:36:00+02:00"
        assert _time_patterns(presc) == []


# --------------------------------------------------------------------------- #
# TimePattern -- interval (E/F) and special (G, H)
# --------------------------------------------------------------------------- #
INTERMITTENT = "7087005"
AS_REQUIRED = "225761000"
CONTINUOUS = "255238004"


class TestTimePatternInterval:
    def test_e_every_n_days(self, transform_request):
        """E: period=3, periodUnit=d -> Intermittent + hasOffset 3 d."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"frequency": 1, "period": 3, "periodUnit": "d"}},
                }
            ],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == INTERMITTENT
        off = _offset(tp)
        assert off is not None and off.get("hasValue") == 3
        assert off.get("hasUnit", {}).get("hasCode", {}).get("termid") == "d"
        assert "hasFrequency" not in tp

    def test_f_every_n_hours(self, transform_request):
        """F: period=6, periodUnit=h -> Intermittent + hasOffset 6 h."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"frequency": 1, "period": 6, "periodUnit": "h"}},
                }
            ],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == INTERMITTENT
        off = _offset(tp)
        assert off is not None and off.get("hasValue") == 6
        assert off.get("hasUnit", {}).get("hasCode", {}).get("termid") == "h"


class TestTimePatternSpecial:
    def test_g_prn_with_min_interval(self, transform_request):
        """G: asNeededBoolean=true + min interval -> As required + hasOffset 6 h."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "asNeededBoolean": True,
                    "timing": {"repeat": {"frequency": 1, "period": 6, "periodUnit": "h"}},
                }
            ],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == AS_REQUIRED
        off = _offset(tp)
        assert off is not None and off.get("hasValue") == 6
        assert off.get("hasUnit", {}).get("hasCode", {}).get("termid") == "h"

    def test_g_bare_prn_type_only(self, transform_request):
        """G: bare asNeededBoolean=true (no repeat) -> As required, no offset/frequency."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[{"doseAndRate": [_ucum_dose(1)], "asNeededBoolean": True}],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == AS_REQUIRED
        assert "hasOffset" not in tp
        assert "hasFrequency" not in tp

    def test_h_infusion_continuous(self, transform_request):
        """H: rateQuantity -> Continuous TypeCode; rate stored in Drug.hasQuantity."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_rate(1000, "mg/h")],
                    "timing": {"repeat": {"boundsPeriod": {"start": "2025-10-31T10:15:00+01:00", "end": "2025-11-01T10:15:00+01:00"}}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        tps = _time_patterns(presc)
        assert len(tps) == 1
        assert _type(tps[0]) == CONTINUOUS
        # rate -> Drug.hasQuantity (rate unit), start/end preserved
        assert presc["hasDrug"]["hasQuantity"]["hasValue"] == 1000
        assert presc["hasDrug"]["hasQuantity"]["hasUnit"]["hasCode"]["termid"] == "mgperh"
        assert presc.get("hasStartDateTime") == "2025-10-31T10:15:00+01:00"
        assert presc.get("hasEndDateTime") == "2025-11-01T10:15:00+01:00"


# --------------------------------------------------------------------------- #
# TimePattern -- complex basic (D weekly, I nDay)
# --------------------------------------------------------------------------- #
class TestTimePatternWeekly:
    def test_d_weekday_subset(self, transform_request):
        """D: dayOfWeek=[mon,wed,fri] -> <count> {#}/wk + Intermittent; off-grid time uncoded."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {"repeat": {"dayOfWeek": ["mon", "wed", "fri"], "timeOfDay": ["09:13:00"]}},
                }
            ],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == INTERMITTENT
        f = _freq(tp)
        assert f.get("hasValue") == 3
        assert f.get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperwk"
        assert "hasTimeOfDayCode" not in tp  # 09:13 off-grid

    def test_d_all_seven_days_is_daily(self, transform_request):
        """D: all 7 weekdays -> treated as daily (1 {#}/d, no typeCode)."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_ucum_dose(1)],
                    "timing": {
                        "repeat": {
                            "dayOfWeek": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                            "timeOfDay": ["08:00:00"],
                        }
                    },
                }
            ],
        )
        result = transform_request(mr)
        tps = _time_patterns(get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]"))
        assert len(tps) == 1
        tp = tps[0]
        assert "hasTypeCode" not in tp
        assert _freq(tp).get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperd"
        assert _tod(tp) == "73775008"  # 08:00 canonical -> Morning


class TestTimePatternNDay:
    def test_i_nday_step(self, transform_request):
        """I: one cycle step (period=4 d, timeOfDay 12:00) -> Intermittent + offset 4 d + Noon."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {
                    "doseAndRate": [_form_dose(2, "CAP")],
                    "timing": {"repeat": {"frequency": 1, "period": 4, "periodUnit": "d", "timeOfDay": ["12:00:00"], "offset": 1}},
                }
            ],
        )
        result = transform_request(mr)
        presc = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription[0]")
        tps = _time_patterns(presc)
        assert len(tps) == 1
        tp = tps[0]
        assert _type(tp) == INTERMITTENT
        off = _offset(tp)
        assert off.get("hasValue") == 4
        assert off.get("hasUnit", {}).get("hasCode", {}).get("termid") == "d"
        assert _tod(tp) == "71997007"  # 12:00 -> Noon
        # dose (CAP) -> {#}
        assert presc["hasDrug"]["hasQuantity"]["hasValue"] == 2

    def test_i_steps_are_separate_prescriptions(self, transform_request):
        """I: each cycle step is its own dosageInstruction -> its own DrugPrescription."""
        mr = make_medication_request(
            medication=make_medication(),
            dosage_instructions=[
                {"doseAndRate": [_form_dose(1, "CAP")], "timing": {"repeat": {"period": 4, "periodUnit": "d", "timeOfDay": ["08:00:00"], "offset": 0}}},
                {"doseAndRate": [_form_dose(2, "CAP")], "timing": {"repeat": {"period": 4, "periodUnit": "d", "timeOfDay": ["12:00:00"], "offset": 1}}},
            ],
        )
        result = transform_request(mr)
        prescs = get_path(result, "DrugPrescriptionEvent[0].hasDrugPrescription")
        assert len(prescs) == 2
        # each carries its own interval TimePattern with offset 4 d
        for p in prescs:
            tp = _time_patterns(p)[0]
            assert _type(tp) == INTERMITTENT
            assert _offset(tp).get("hasValue") == 4
