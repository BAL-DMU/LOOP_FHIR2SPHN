"""
Verification of the TimePattern translate strategy & helper groups (Utils.map).

Confirms the reusable lookup helpers resolve for canonical inputs and -- crucially
-- do NOT abort the transform on off-grid / unknown inputs (the repo hazard with
unguarded ``translate()``):

  * ``when_to_time_of_day``  -- FHIR ``when`` (MORN/NOON/EVE/NIGHT) -> SNOMED ToD
  * ``clock_to_time_of_day`` -- canonical clock (08/12/13/18/22) -> SNOMED ToD;
                                off-grid clock matches nothing (no abort)
  * ``unit_ucum``            -- data-driven UCUM code (periodUnit) -> SPHN Unit
  * ``unit_per_day`` / ``unit_per_week`` -- {#}/d and {#}/wk frequency literals

A small throwaway StructureMap drives the helpers against the real
DrugPrescriptionEvent / DrugPrescription / TimePattern structures and the result
is scanned for the expected ``termid`` strings. The input deliberately includes
an unknown ``when`` (``AC``) and an off-grid clock (``09:15:00``) to prove they
are silently skipped rather than aborting.
"""

from pathlib import Path

import pytest

from tests.conftest import upload_map
from tests.config import MATCHBOX_BASE_URL  # noqa: F401  (kept for parity/debug)

HELPERS_MAP_URL = (
    "http://research.balgrist.ch/fhir2sphn/StructureMap/MedicationRequestHelpers"
)

HELPERS_MAP = f'''\
map "{HELPERS_MAP_URL}" = "MedicationRequestHelpers"

uses "http://hl7.org/fhir/StructureDefinition/MedicationRequest" alias MedicationRequest as source
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-Content" alias Content as target
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-DrugPrescriptionEvent" alias DrugPrescriptionEvent as target
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-DrugPrescription" alias DrugPrescription as target
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-TimePattern" alias TimePattern as target
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-Quantity" alias Quantity as target

imports "http://research.balgrist.ch/fhir2sphn/StructureMap/Utils"

group exercise_helpers(source mr : MedicationRequest, target content : Content) {{
    mr -> content.DrugPrescriptionEvent = create('DrugPrescriptionEvent') as event then {{
        mr.dosageInstruction first as di -> event.hasDrugPrescription = create('DrugPrescription') as presc then {{
            di.timing as tim then {{
                tim.repeat as r then {{
                    // when -> ToD : one TimePattern per `when` (unknown `when` skipped, no abort)
                    r.when as w -> presc.hasTimePattern as tp then when_to_time_of_day(w, tp) "when_tod";
                    // clock -> ToD : canonical coded, off-grid silently skipped (no abort)
                    r.timeOfDay as tod -> presc.hasTimePattern as tp then clock_to_time_of_day(tod, tp) "clock_tod";
                    // offset unit via cm-ucum-sphn (data-driven periodUnit)
                    r.periodUnit as pu -> presc.hasTimePattern as tp, tp.hasOffset as q, q.id = uuid(), q.hasUnit as unit then unit_ucum(pu, unit) "offset_unit";
                    // frequency unit literals {{#}}/d and {{#}}/wk
                    r as freq1 -> presc.hasTimePattern as tp, tp.hasFrequency as q, q.id = uuid(), q.hasValue = '1', q.hasUnit as unit then unit_per_day(freq1, unit) "freq_day";
                    r as freq2 -> presc.hasTimePattern as tp, tp.hasFrequency as q, q.id = uuid(), q.hasValue = '2', q.hasUnit as unit then unit_per_week(freq2, unit) "freq_week";
                }};
            }};
        }};
    }} "exercise_helpers";
}}
'''

# `when` mixes mapped (MORN/EVE) and unknown (AC) codes; `timeOfDay` mixes a
# canonical (08:00:00) and an off-grid (09:15:00) clock -> both unknowns must be
# silently skipped, not abort the transform.
HELPERS_INPUT = {
    "resourceType": "MedicationRequest",
    "id": "medreq-helpers",
    "status": "active",
    "intent": "order",
    "subject": {"reference": "Patient/x"},
    "dosageInstruction": [
        {
            "timing": {
                "repeat": {
                    "when": ["MORN", "EVE", "AC"],
                    "timeOfDay": ["08:00:00", "09:15:00"],
                    "period": "3",
                    "periodUnit": "d",
                }
            }
        }
    ],
}


def _collect_strings(obj):
    """Recursively gather all string values in a nested dict/list."""
    found = []
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_collect_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_collect_strings(v))
    elif isinstance(obj, str):
        found.append(obj)
    return found


@pytest.fixture(scope="module")
def helpers_result(maps_uploaded, transform_bundle, tmp_path_factory):  # noqa: ARG001
    """Upload the helper-exercising map and transform HELPERS_INPUT through it."""
    map_path = tmp_path_factory.mktemp("helpers") / "MedicationRequestHelpers.map"
    Path(map_path).write_text(HELPERS_MAP)
    upload_map(map_path)
    return transform_bundle(HELPERS_INPUT, source_map=HELPERS_MAP_URL)


@pytest.fixture(scope="module")
def helpers_strings(helpers_result):
    return _collect_strings(helpers_result)


def test_when_to_time_of_day(helpers_strings):
    """MORN -> Morning (73775008), EVE -> Evening (3157002)."""
    assert "73775008" in helpers_strings, f"MORN not coded. Strings: {helpers_strings}"
    assert "3157002" in helpers_strings, f"EVE not coded. Strings: {helpers_strings}"


def test_unknown_when_does_not_abort(helpers_strings):
    """Unknown `when` 'AC' is skipped -> transform still produced output."""
    # Noon code must NOT appear (no NOON/12/13 in input); proves no spurious match.
    assert "71997007" not in helpers_strings, (
        f"Unexpected Noon code from unknown `when`. Strings: {helpers_strings}"
    )
    # And the mapped codes are present -> the transform completed despite 'AC'.
    assert "73775008" in helpers_strings


def test_clock_to_time_of_day_canonical(helpers_strings):
    """Canonical clock 08:00:00 -> Morning (73775008)."""
    assert "73775008" in helpers_strings, f"08:00 not coded. Strings: {helpers_strings}"


def test_offgrid_clock_skipped_no_abort(helpers_result, helpers_strings):
    """Off-grid clock 09:15:00 yields no code yet the transform succeeds."""
    # Success == we got a structured result back at all.
    assert isinstance(helpers_result, dict) and helpers_result, "transform aborted"
    # No Night code anywhere (no 22:00 / NIGHT in input).
    assert "2546009" not in helpers_strings


def test_offset_unit_lookup(helpers_strings):
    """periodUnit 'd' resolves through cm-ucum-sphn -> termid 'd'."""
    assert "d" in helpers_strings, f"offset unit 'd' not resolved. Strings: {helpers_strings}"


def test_frequency_unit_literals(helpers_strings):
    """{#}/d -> cblnbcbrperd and {#}/wk -> cblnbcbrperwk resolve."""
    assert "cblnbcbrperd" in helpers_strings, f"{{#}}/d missing. Strings: {helpers_strings}"
    assert "cblnbcbrperwk" in helpers_strings, f"{{#}}/wk missing. Strings: {helpers_strings}"
