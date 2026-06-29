"""
De-risk spike for the MedicationRequest -> DrugPrescriptionEvent converter.

Verifies two uncertain FML/Matchbox facts BEFORE building the real map:

  (a) Source-system numerics arrive as JSON *strings* (e.g. ``count:"1"``,
      ``doseQuantity.value:"2.0"``). Confirm Matchbox parses/coerces them so a
      *numeric* ``where`` guard (``where $this = 1``, ``where $this.value >= 2``)
      fires. The whole pattern-discrimination design relies on numeric compares.

  (b) ``evaluate(r, dayOfWeek.count())`` (FHIRPath ``count()``) is supported on
      Matchbox/HAPI — needed for the Weekly shape (count the weekdays).

This is a throwaway spike: it uploads a tiny self-contained StructureMap
(``MedicationRequestSpike``) that targets the already-present
``DrugAdministrationEvent`` SD and uses ``id`` / ``hasStartDateTime`` /
``hasEndDateTime`` as readback channels. No production maps or SDs are modified.
"""

from pathlib import Path

import pytest

from tests.conftest import upload_map
from tests.config import MATCHBOX_BASE_URL

SPIKE_MAP_URL = "http://research.balgrist.ch/fhir2sphn/StructureMap/MedicationRequestSpike"

# Throwaway map. Three readback markers, each fires only if the corresponding
# fact holds:
#   - event.id               = "wd<n>"    <- FHIRPath count() over dayOfWeek (b)
#   - event.hasStartDateTime = INT_MARKER <- numeric guard on string "1"      (a)
#   - event.hasEndDateTime   = DEC_MARKER <- numeric guard on string "2.0"    (a)
SPIKE_MAP = f'''\
map "{SPIKE_MAP_URL}" = "MedicationRequestSpike"

uses "http://hl7.org/fhir/StructureDefinition/MedicationRequest" alias MedicationRequest as source
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-Content" alias Content as target
uses "http://research.balgrist.ch/fhir2sphn/StructureDefinition/SPHN-DrugAdministrationEvent" alias DrugAdministrationEvent as target

group spike(source mr : MedicationRequest, target content : Content) {{
    mr -> content.DrugAdministrationEvent = create('DrugAdministrationEvent') as event then {{
        mr.dosageInstruction first as di then {{
            di.timing as t then {{
                t.repeat as r then {{
                    // (b) FHIRPath count() over dayOfWeek -> readable string id
                    r -> event.id = evaluate(r, 'wd' & dayOfWeek.count().toString()) "wd_count";
                    // (a) integer coercion: repeat.count is JSON string "1" -> numeric compare
                    r.count as c where $this = 1 -> event.hasStartDateTime = '2000-01-01T00:00:00+00:00' "int_coerce";
                }};
            }};
            // (a) decimal coercion: doseQuantity.value is JSON string "2.0" -> numeric compare
            di.doseAndRate as dr then {{
                dr.doseQuantity as q where $this.value >= 2 -> event.hasEndDateTime = '2000-02-02T00:00:00+00:00' "dec_coerce";
            }};
        }};
    }} "spike";
}}
'''

# A MedicationRequest whose numerics are all JSON strings (as the source system
# emits them) and with 3 dayOfWeek entries -> count() must yield 3.
SPIKE_INPUT = {
    "resourceType": "MedicationRequest",
    "id": "medreq-spike",
    "status": "active",
    "intent": "order",
    "subject": {"reference": "Patient/x"},
    "dosageInstruction": [
        {
            "timing": {
                "repeat": {
                    "count": "1",
                    "dayOfWeek": ["mon", "wed", "fri"],
                }
            },
            "doseAndRate": [
                {
                    "doseQuantity": {
                        "value": "2.0",
                        "unit": "Capsule",
                        "system": "http://terminology.hl7.org/CodeSystem/v3-orderableDrugForm",
                        "code": "CAP",
                    }
                }
            ],
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
def spike_result(maps_uploaded, transform_bundle, tmp_path_factory):  # noqa: ARG001
    """Upload the throwaway spike map and transform SPIKE_INPUT through it."""
    map_path = tmp_path_factory.mktemp("spike") / "MedicationRequestSpike.map"
    Path(map_path).write_text(SPIKE_MAP)
    upload_map(map_path)
    return transform_bundle(SPIKE_INPUT, source_map=SPIKE_MAP_URL)


def test_fhirpath_count_supported(spike_result):
    """(b) evaluate(r, dayOfWeek.count()) works -> id == 'wd3'."""
    strings = _collect_strings(spike_result)
    assert "wd3" in strings, (
        "FHIRPath count() not honoured (expected id 'wd3'). "
        f"Strings in result: {strings}"
    )


def test_integer_string_coerces_for_numeric_where(spike_result):
    """(a) repeat.count JSON string '1' coerces so `where $this = 1` fires."""
    strings = _collect_strings(spike_result)
    assert any(s.startswith("2000-01-01") for s in strings), (
        "Numeric `where $this = 1` did NOT fire on string count '1' "
        f"-> integer coercion fails. Strings in result: {strings}"
    )


def test_decimal_string_coerces_for_numeric_where(spike_result):
    """(a) doseQuantity.value JSON string '2.0' coerces so `where >= 2` fires."""
    strings = _collect_strings(spike_result)
    assert any(s.startswith("2000-02-02") for s in strings), (
        "Numeric `where $this.value >= 2` did NOT fire on string value '2.0' "
        f"-> decimal coercion fails. Strings in result: {strings}"
    )
