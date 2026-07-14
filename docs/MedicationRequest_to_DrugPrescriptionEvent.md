# Timing patterns: FHIR R4 → SPHN

Reference for the `MedicationRequest → DrugPrescriptionEvent` converter
(`maps/MedicationRequestToDrugPrescriptionEvent.map`; TimePattern helpers in `maps/Utils.map`).
For each dosage/timing pattern this documents the **two representations**:

1. **FHIR R4** — the incoming `MedicationRequest.dosageInstruction[].timing` (and `doseAndRate`).
2. **SPHN 2026.1** — the `DrugPrescription` / `TimePattern` produced by the converter.

> How these Bundles are produced upstream is documented in the LoopExtraction repo
> (`mappings_docs/MedicationRequest/Readme.md`), using the same pattern letters A–K.
> Counts below are from the sample data in `puk-leomed-services/tests/testdata/input/*medication_request*.json` (9 Bundles, 66 dosageInstructions).

---

## Mapping overview (brief)

One FHIR `MedicationRequest` → one SPHN **DrugPrescriptionEvent**.

```
MedicationRequest                          DrugPrescriptionEvent
  meta.source              ───────────────►  hasSourceSystem
  id                       ───────────────►  id  ("MedicationRequest/<id>")
  authoredOn               ───────────────►  hasDateTime            (1..1)
  encounter                ───────────────►  hasAdministrativeCase
  subject                  ───────────────►  (SubjectPseudoIdentifier — Bundle level)
                                             hasDrugPrescription    (1..n)
  each dosageInstruction[] ───────────────►    └─ one DrugPrescription
    contained[Medication]  ───────────────►        hasDrug   (code/GTIN, form→doseForm, ingredients→substance) — reuses DrugAdmin logic
    doseAndRate.doseQuantity ─────────────►        hasDrug.hasQuantity
    doseAndRate.rateQuantity ─────────────►        hasDrug.hasQuantity
    timing.repeat.boundsPeriod.start/end ─►        hasStartDateTime / hasEndDateTime
    timing.event (single)  ───────────────►        hasStartDateTime & hasEndDateTime  (both = event)
    route (absent in sample data) ────────►        hasAdministrationRouteCode  (defensive)
    timing.repeat / event / asNeededBoolean ──►    hasTimePattern   (0..n)   ◄── see "Pattern detail" below
```

**Key rules**
- **Required-attribute guard.** SPHN requires `hasDateTime` (1..1), `hasDrugPrescription` (1..*) and `DrugPrescription.hasDrug` (1..1). A `MedicationRequest` missing `authoredOn`, `dosageInstruction` or a contained `Medication` therefore produces **no DrugPrescriptionEvent at all** (it would be structurally invalid).
- **One `DrugPrescription` per `dosageInstruction`.** A single instruction with several `when` values yields one DrugPrescription with several `TimePattern`s.
- Drug & substance quantities are expressed **per planned administration** (SPHN convention).
- `DrugPrescriptionEvent.hasDateTime` is **always** `authoredOn` (1..1); per-administration times go on `DrugPrescription.hasStartDateTime`/`hasEndDateTime`. `timing.event` and `repeat.boundsPeriod` are mutually exclusive in the input data (the bounds branch is guarded by `event.empty()`), so the 0..1 date fields are never double-assigned.
- **A `TimePattern` must carry ≥1 property.** If a pattern yields no `hasTypeCode` *and* no `hasFrequency`/`hasOffset`/`hasTimeOfDayCode` (patterns A, J), **omit the entire TimePattern node** — never emit an empty one. (`TimePattern.hasTypeCode` is `0..1` in 2026.1; the repo FSH was relaxed from `1..1` to `0..1` accordingly.)
- FML has no if/else — sibling `where` rules all fire, so each timing shape needs a mutually-exclusive guard (or use one nested dispatch). PRN (`asNeededBoolean=true`) overlaps interval shapes, so non-PRN rules must exclude PRN with `asNeededBoolean.where($this = true).empty()` — a plain `!= true` would wrongly drop the common case where `asNeededBoolean` is *absent* (FHIRPath `{} != true` is empty, i.e. false-y).
- Dose units arrive in two FHIR systems and are normalised exactly as in the DrugAdministration map: UCUM (`mg`, `mL`, `[IU]`, `{#}`) and orderable drug form (`TAB`, `CAP`, `DROP`, … → UCUM `{#}` via the `unit_number` helper).
- The **`timing` → `TimePattern`** decoding is the core of this converter and is detailed per pattern below.

---

## Code references

### TimePattern.hasTypeCode — SNOMED CT (value set restricted in 2026.1)
| Code | Meaning |
|------|---------|
| `255238004` | Continuous (qualifier value) |
| `7087005` | Intermittent (qualifier value) |
| `225761000` | As required (qualifier value) — PRN / *pro re nata* |

### TimePattern.hasTimeOfDayCode — SNOMED CT (descendant of `272106006 | Temporal periods of day |`)
| Code | Meaning | Canonical clock | Bucket (clock → code) |
|------|---------|-------------------------------|------------------------|
| `73775008` | Morning | 08:00 | 06:00–11:59 |
| `71997007` | Noon | 12:00 / 13:00 | 12:00–13:59 |
| `255213009` | During afternoon | — | 14:00–17:59 |
| `3157002` | Evening | 18:00 | 18:00–21:59 |
| `2546009` | Night time | 22:00 | 22:00–05:59 |

> **No exact-time slot exists in SPHN.** Every clock time is coarsened to the day-part bucket covering it (`clock_to_time_of_day` in `Utils.map`). The exact time is lost; a malformed value matches no bucket → no code, no abort. FHIR `when` codes (`MORN`/`NOON`/`EVE`/`NIGHT`) map 1:1 via `when_to_time_of_day` — `AFT` and other `when` codes remain unmapped.

### UCUM units used (SPHN value sets)
- `hasFrequency` — SPHN allows `{#}/h`, `{#}/d`, `{#}/wk`, `{#}/mo`, `{#}/a` (no sub-h). The converter only ever emits `{#}/d` and `{#}/wk` (hardcoded in the `unit_per_day`/`unit_per_week` helpers; hourly dosing → `hasOffset`).
- `hasOffset` — SPHN allows `a`, `d`, `h`, `min`, `mo`, `wk` (no `s`/`ms`); all present in `cm-ucum-sphn`, reused directly on FHIR `periodUnit`.
- `hasDuration` — SPHN allows `a`, `d`, `mo`, `wk`.
- Rate (infusion) in `Drug.hasQuantity`: e.g. `mg/h` (already in `cm-ucum-sphn`).

---

## Summary

| # | Shape | FHIR `timing` signature | SPHN result | Loss |
|---|-------|-------------------------|-------------|------|
| A | One-off dose | `timing.event=[ts]` (single; no boundsPeriod/count) | no TimePattern; `DrugPrescription.hasStartDateTime = hasEndDateTime = event` (`hasDateTime` = authoredOn) | — |
| B | Daily, day-parts | `freq=1, period=1, periodUnit=d, when=[…]` | per `when`: TP `1 {#}/d` + `hasTimeOfDayCode` | — |
| C | Daily, clock times | `freq=1, period=1, periodUnit=d, timeOfDay=[…]` | TP `1 {#}/d` + ToD code (clock bucketed to day-part) | exact clock time (coarsened to day-part) |
| D | Weekly | `dayOfWeek=[…], timeOfDay=[…]` | `=7`→`1 {#}/d`; `<7`→`<count> {#}/wk` + Intermittent (+ToD) | *which* weekdays |
| E | Every N days | `freq=1, period=N>1, periodUnit=d` | TP `hasOffset = N d` + Intermittent | — |
| F | Every N hours | `freq=1, period=N>1, periodUnit=h` | TP `hasOffset = N h` + Intermittent | — |
| G | PRN / as-needed | `asNeededBoolean=true` (± min-interval `freq/period`) | TP `hasTypeCode = As required` (± offset) | — |
| H | Continuous infusion | `doseAndRate.rateQuantity` (e.g. `mg/h`), `boundsPeriod{start,end}` | TP `Continuous`; rate → `Drug.hasQuantity` (rate unit); start/end | rate semantics overload `hasQuantity` |
| I | n-day cycle | `freq=1, period=cycleLen>1, periodUnit=d, offset=relDay, timeOfDay=[…]`, rising dose/step | each step = own DrugPrescription, reuse every-N-days: `hasOffset = cycleLen d` + Intermittent (+ToD) | cycle phase (`repeat.offset`), step linkage |
| J | Absolute scheduled time | `timing.event=[abs ts]` (single; no boundsPeriod), no frequency | single time point: `hasStartDateTime = hasEndDateTime = event`; no TimePattern | — |
| K | Bare daily | `freq=1, period=1, periodUnit=d` only | TP `1 {#}/d`, no ToD | — |

> **Reliable signals to disambiguate:** A and J BOTH arrive as a single `timing.event` — they are indistinguishable downstream and need no disambiguation from each other (both map to `hasStartDateTime = hasEndDateTime = event`, no TimePattern). PRN = `asNeededBoolean=true` (**not** `timing.event`); infusion = `rateQuantity`.

---

## Pattern detail

### A — One-off dose (single `timing.event`)
Single one-off dose.

**FHIR**
```json
{
  "timing": { "event": [ "2024-10-15T14:18:00+02:00" ] },
  "asNeededBoolean": false,
  "doseAndRate": [ { "doseQuantity": { "value": 1, "code": "TAB",
                     "system": "http://terminology.hl7.org/CodeSystem/v3-orderableDrugForm" } } ]
}
```

**SPHN** — no TimePattern (spec exception: single quantity at a single time point).
`hasDateTime` is always `authoredOn`; the dose time goes on the DrugPrescription. A single
`timing.event` is the whole window, so it fills BOTH start and end.
```
DrugPrescriptionEvent.hasDateTime = <authoredOn>
  hasDrugPrescription
    hasDrug.hasQuantity = 1 {#}                       # TAB → {#}
    hasStartDateTime = 2024-10-15T14:18:00+02:00      # = event
    hasEndDateTime   = 2024-10-15T14:18:00+02:00      # = event
    (no hasTimePattern)                               # omit empty TimePattern node
```

---

### B — Daily at day-parts (`repeat.when`)
Daily at named day-parts ("1-1-1-0" style). One `dosageInstruction` may list several `when` values.

**FHIR**
```json
{ "timing": { "repeat": { "boundsPeriod": { "start": "2024-12-03T15:30:00+01:00" },
                          "frequency": 1, "period": 1, "periodUnit": "d",
                          "when": ["MORN", "EVE"] } },
  "doseAndRate": [ { "doseQuantity": { "value": 1, "code": "{#}", "system": "http://unitsofmeasure.org" } } ] }
```

**SPHN** — one `TimePattern` per `when`, sharing the DrugPrescription/quantity.
```
hasDrugPrescription
  hasDrug.hasQuantity = 1 {#}
  hasStartDateTime = 2024-12-03T15:30:00+01:00   # boundsPeriod.start
  hasTimePattern   # MORN
    hasFrequency = 1 {#}/d
    hasTimeOfDayCode = 73775008 | Morning
  hasTimePattern   # EVE
    hasFrequency = 1 {#}/d
    hasTimeOfDayCode = 3157002 | Evening
```

---

### C — Daily at explicit clock times (`repeat.timeOfDay`)
Daily at explicit clock times. Every clock time is bucketed into a day-part `hasTimeOfDayCode` (see bucket table above).

**FHIR**
```json
{ "timing": { "repeat": { "frequency": 1, "period": 1, "periodUnit": "d",
                          "timeOfDay": ["08:00:00"] } },
  "doseAndRate": [ { "doseQuantity": { "value": 2, "code": "TAB", "system": "…/v3-orderableDrugForm" } } ] }
```

**SPHN**
```
hasTimePattern
  hasFrequency = 1 {#}/d
  hasTimeOfDayCode = 73775008 | Morning      # 08:00:00 → 06:00–11:59 bucket
```
Non-canonical example (`13:55:00`): `hasFrequency = 1 {#}/d`, `hasTimeOfDayCode = 71997007 | Noon` (12:00–13:59 bucket); `15:30:00` → `255213009 | During afternoon`.

---

### D — Weekly / weekday subset (`repeat.dayOfWeek`)

**FHIR**
```json
{ "timing": { "repeat": { "dayOfWeek": ["mon", "wed", "fri"],
                          "timeOfDay": ["09:13:00"] } } }
```

**SPHN** — count the weekdays (FHIRPath `dayOfWeek.count()`).
```
hasTimePattern
  hasTypeCode  = 7087005 | Intermittent       # because subset (<7)
  hasFrequency = 3 {#}/wk                      # 3 of 7 days
  hasTimeOfDayCode = 73775008 | Morning        # 09:13:00 → 06:00–11:59 bucket
```
All-7-days (`mon..sun`) → `hasFrequency = 1 {#}/d` (treated as daily, no typeCode).
**Loss:** the specific weekdays (no SPHN concept) — only the count survives.

---

### E / F — Interval, every N days / hours (`repeat.period > 1`)
Interval dosing. `repeat.offset` of SPHN = "time between events".

**FHIR (E, days)** — every 3 days
```json
{ "timing": { "repeat": { "frequency": 1, "period": 3, "periodUnit": "d" } } }
```
**FHIR (F, hours)** — every 6 hours
```json
{ "timing": { "repeat": { "frequency": 1, "period": 6, "periodUnit": "h" } } }
```

**SPHN**
```
hasTimePattern
  hasTypeCode = 7087005 | Intermittent
  hasOffset   = 3 d        # (E)   /   6 h   (F)
```

---

### G — PRN / as-needed (`asNeededBoolean=true`)
As-needed (*pro re nata*). Driven by `asNeededBoolean=true`.

**FHIR**
```json
{ "asNeededBoolean": true,
  "timing": { "repeat": { "boundsPeriod": { "start": "…" },
                          "frequency": 1, "period": 6, "periodUnit": "h" } } }
```

**SPHN**
```
hasTimePattern
  hasTypeCode = 225761000 | As required
  hasOffset   = 6 h        # min spacing, if a min interval was given
```
> "As required" means *up to* the prescribed dose only when needed — not *ad libitum*.

---

### H — Continuous infusion (`doseAndRate.rateQuantity`)

**FHIR**
```json
{ "timing": { "repeat": { "boundsPeriod": { "start": "2025-10-31T10:15:00+01:00",
                                            "end":   "2025-11-01T10:15:00+01:00" } } },
  "doseAndRate": [ { "rateQuantity": { "value": 1000, "code": "mg/h",
                     "system": "http://unitsofmeasure.org" } } ] }
```

**SPHN** — rate stored in `Drug.hasQuantity` (knowingly overloads "per planned administration").
```
hasDrugPrescription
  hasDrug.hasQuantity = 1000 mg/h        # rate unit via cm-ucum-sphn
  hasStartDateTime = 2025-10-31T10:15:00+01:00
  hasEndDateTime   = 2025-11-01T10:15:00+01:00
  hasTimePattern
    hasTypeCode = 255238004 | Continuous
```

---

### I — n-day cycle (interval + `repeat.offset`)
Cycle of steps with differing dose; each step arrives as a separate `dosageInstruction`.

**FHIR (one step of a 4-day cycle)**
```json
{ "timing": { "repeat": { "frequency": 1, "period": 4, "periodUnit": "d",
                          "timeOfDay": ["12:00:00"], "offset": 1 } },
  "doseAndRate": [ { "doseQuantity": { "value": 2, "code": "CAP", "system": "…/v3-orderableDrugForm" } } ] }
```

**SPHN** — each step → its own DrugPrescription (one per `dosageInstruction`), reusing the every-N-days decoder.
```
hasDrugPrescription        # this step
  hasDrug.hasQuantity = 2 {#}
  hasTimePattern
    hasTypeCode = 7087005 | Intermittent
    hasOffset   = 4 d
    hasTimeOfDayCode = 71997007 | Noon       # 12:00:00 → 12:00–13:59 bucket
```
**Loss:** FHIR `repeat.offset` (which day in the cycle / phase) is not read; steps are not linked as one cycle.

---

### J — Absolute scheduled time (single `timing.event`)
Discrete planned administrations at absolute datetimes (one `event` per instruction in the data).

**FHIR**
```json
{ "timing": { "event": ["2025-05-07T22:36:00+02:00"] },
  "doseAndRate": [ { "doseQuantity": { "value": 2, "code": "{#}", "system": "http://unitsofmeasure.org" } } ] }
```

> This shape carries exactly ONE `timing.event` and no `repeat`/`boundsPeriod`/`count` — structurally identical to A. A single event is the whole window, so it fills BOTH `hasStartDateTime` and `hasEndDateTime`.

**SPHN** — treat like a single time point.
```
hasDrugPrescription
  hasDrug.hasQuantity = 2 {#}
  hasStartDateTime = 2025-05-07T22:36:00+02:00   # = event
  hasEndDateTime   = 2025-05-07T22:36:00+02:00   # = event
  (no hasTimePattern)                            # omit empty TimePattern node
```

---

### K — Bare daily / QD
Daily dosing with no day-part and no clock time.

**FHIR**
```json
{ "timing": { "repeat": { "frequency": 1, "period": 1, "periodUnit": "d" } } }
```
**SPHN**
```
hasTimePattern
  hasFrequency = 1 {#}/d
  # no hasTimeOfDayCode
```
