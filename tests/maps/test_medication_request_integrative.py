"""
Integrative end-to-end test for the MedicationRequest -> DrugPrescriptionEvent converter.

Unlike the focused unit tests (which transform a MedicationRequest directly through the
map), this drives a full FHIR Bundle through the wired ``BundleToLoopSphn`` pipeline and
spot-checks that the new converter is dispatched and produces the expected SPHN concepts.

The recommended rich real Bundle (``df1be82…``) lives in the external
``puk-leomed-services`` repo and is not vendored here, so this uses a synthetic but
realistically rich MedicationRequest: one contained Medication and several
dosageInstructions spanning the once / day-part / clock / every-N-days / every-N-hours /
weekly / infusion / multiplan shapes -- each becoming its own DrugPrescription.
"""

import pytest

from tests.helpers import get_path
from tests.maps.test_medication_request_to_drug_prescription_event import (
    make_medication,
    _ucum_dose,
    _form_dose,
    _rate,
    _time_patterns,
    _type,
    _tod,
    _offset,
    _freq,
    INTERMITTENT,
    CONTINUOUS,
)

AUTHORED_ON = "2025-01-20T09:00:00+01:00"


def _rich_medication_request():
    """One MedicationRequest, one contained Medication, many dosageInstructions (shapes A,B,C,E,F,H,D,J)."""
    med = make_medication(
        gtin_code="7680123456789",
        medication_name="Rich Drug 10mg",
        ingredient_snomed="387458008",
        ingredient_text="Acetylsalicylic acid",
        form_code="TAB",
        form_display="Tablet",
    )
    return {
        "resourceType": "MedicationRequest",
        "id": "medreq-rich",
        "meta": {"source": "http://pukzh.ch/kisim"},
        "status": "active",
        "intent": "order",
        "subject": {"reference": "Patient/test-patient-1"},
        "encounter": {"reference": "Encounter/enc-9"},
        "authoredOn": AUTHORED_ON,
        "contained": [med],
        "medicationReference": {"reference": f"#{med['id']}"},
        "dosageInstruction": [
            # A -- Once (single point-in-time event)
            {"doseAndRate": [_form_dose(1, "TAB")], "asNeededBoolean": False,
             "timing": {"event": ["2025-01-20T14:18:00+01:00"]}},
            # B -- Schema / day-parts
            {"doseAndRate": [_form_dose(1, "TAB")],
             "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d", "when": ["MORN", "EVE"]}}},
            # C -- Schedule / clock (canonical)
            {"doseAndRate": [_form_dose(2, "TAB")],
             "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d", "timeOfDay": ["08:00:00"]}}},
            # E -- every N days
            {"doseAndRate": [_form_dose(1, "TAB")],
             "timing": {"repeat": {"frequency": 1, "period": 3, "periodUnit": "d"}}},
            # F -- every N hours
            {"doseAndRate": [_ucum_dose(1, "mg")],
             "timing": {"repeat": {"frequency": 1, "period": 6, "periodUnit": "h"}}},
            # H -- continuous infusion
            {"doseAndRate": [_rate(1000, "mg/h")],
             "timing": {"repeat": {"boundsPeriod": {"start": "2025-01-21T10:00:00+01:00", "end": "2025-01-22T10:00:00+01:00"}}}},
            # D -- weekly subset
            {"doseAndRate": [_form_dose(1, "TAB")],
             "timing": {"repeat": {"dayOfWeek": ["mon", "wed", "fri"], "timeOfDay": ["08:00:00"]}}},
            # J -- multiplan (single absolute event)
            {"doseAndRate": [_form_dose(2, "TAB")],
             "timing": {"event": ["2025-01-23T22:36:00+01:00"]}},
        ],
    }


@pytest.fixture
def rich_result(transform_bundle, make_bundle, base_patient):
    bundle = make_bundle(base_patient, _rich_medication_request())
    return transform_bundle(bundle)


def _all_prescriptions(result):
    return get_path(result, "content.DrugPrescriptionEvent[0].hasDrugPrescription")


def test_bundle_transforms_and_dispatches(rich_result):
    """The wired pipeline produces a DrugPrescriptionEvent from the MedicationRequest."""
    event = get_path(rich_result, "content.DrugPrescriptionEvent[0]")
    assert event is not None
    assert event.get("id") == "MedicationRequest/medreq-rich"
    assert event.get("hasDateTime") == AUTHORED_ON
    assert event.get("hasSourceSystem") is not None
    assert event.get("hasAdministrativeCase") is not None


def test_one_prescription_per_instruction(rich_result):
    prescriptions = _all_prescriptions(rich_result)
    assert isinstance(prescriptions, list) and len(prescriptions) == 8


def test_source_system_created_at_bundle_level(rich_result):
    """meta.source -> bundle-level SourceSystem (unchanged envelope wiring)."""
    assert get_path(rich_result, "content.SourceSystem[0]") is not None


def test_key_timepatterns_present(rich_result):
    """Spot-check that representative shapes decoded correctly somewhere in the result."""
    prescriptions = _all_prescriptions(rich_result)
    all_tps = [tp for p in prescriptions for tp in _time_patterns(p)]

    type_codes = {_type(tp) for tp in all_tps}
    assert INTERMITTENT in type_codes  # E / F / D subset
    assert CONTINUOUS in type_codes  # H infusion

    tods = {_tod(tp) for tp in all_tps}
    assert "73775008" in tods  # Morning (B / C / D)
    assert "3157002" in tods  # Evening (B)

    # at least one offset (E 3 d or F 6 h) and one weekly frequency (D)
    offsets = [_offset(tp) for tp in all_tps if _offset(tp) is not None]
    assert any(o.get("hasUnit", {}).get("hasCode", {}).get("termid") in {"d", "h"} for o in offsets)
    freqs = [_freq(tp) for tp in all_tps if _freq(tp) is not None]
    assert any(f.get("hasUnit", {}).get("hasCode", {}).get("termid") == "cblnbcbrperwk" for f in freqs)


def test_once_and_multiplan_have_no_timepattern(rich_result):
    """A (Once) and J (Multiplan) are single point events: start == end, no TimePattern."""
    prescriptions = _all_prescriptions(rich_result)
    # the two prescriptions whose drug quantity comes with a start but no TimePattern
    no_tp = [p for p in prescriptions if not _time_patterns(p)]
    # exactly A and J yield no TimePattern
    assert len(no_tp) == 2
    assert all(p.get("hasStartDateTime") is not None for p in no_tp)
    # a single event is the whole window: hasStartDateTime == hasEndDateTime
    assert all(p.get("hasStartDateTime") == p.get("hasEndDateTime") for p in no_tp)
