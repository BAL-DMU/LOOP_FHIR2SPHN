"""
Tests for ImagingStudyToImagingProcedure.map

Tests the ImagingStudy -> ImagingProcedure mapping including:
- identifier (use = secondary) -> id (prefixed 'ImagingProcedure/'); without one,
                                  id falls back to 'ImagingStudy/' + resource id
- meta.source                  -> hasSourceSystem
- started                      -> hasStartDateTime
- modality                     -> hasCode (cm-acquisitionModality, DICOM -> SNOMED);
                                  studies with no mapped modality are skipped
- bundle Patient.identifier     -> not mapped anywhere: the procedure, series and
                                  BodyPosition are top-level, so the connector injects it
- series                       -> top-level content.<SPHN series class> (CT, MR,
                                  PET, X-ray by modality; anything else in scope:
                                  content.ImagingSeries), linked from
                                  hasImagingSeries as {id, target_concept}; uid -> id,
                                  description, started, modality -> dcm:
                                  hasImagingModalityCode, numberOfInstances ->
                                  hasNumberOfFrames, study meta.source -> hasSourceSystem;
                                  series without uid are skipped
- series (CT/MR/PET/X-ray)     -> top-level content.BodyPosition from DICOM Patient
                                  Position (0018,5100), cm-patientPosition, linked from
                                  the series as hasBodyPosition {id}
- series.instance              -> hasImagingFrame nested in the series (uid -> id, no
                                  target_concept); with exactly one instance, the
                                  series DICOM tags give hasType (Image Type,
                                  cm-imagingFrameType), hasContentQualification
                                  and hasStartDateTime (Acquisition DateTime, or
                                  Date + Time), and the nested hasImageDimensions,
                                  hasAnatomicalProjection, hasBodySite,
                                  hasAlgorithm and hasImagingMetric

Note on Code shapes: hasCode (a list, 1..* on ImagingProcedure),
hasImagingModalityCode (a dcm: code) and BodyPosition.hasCode (a snomed: code)
all use the SPHN iri + termid shape, so assert_code_mapped applies to all three.
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_list_length,
    assert_path_equals,
    assert_path_exists,
    assert_quantity_mapped,
    assert_reference,
    get_path,
)

DICOM_SYSTEM = "http://dicom.nema.org/resources/ontology/DCM"
DICOM_EXTENSION_URL = "https://research.balgrist.ch/HDR/fhir/StructureDefinition/DICOM"
SNOMED_ID_SYSTEM = "http://snomed.info/id"
PATIENT_POSITION_TAG = "00185100"
DICOM_SOURCE = "https://research.balgrist.ch/HDR/DICOM"
SUBJECT_REFERENCE = "Patient?identifier=RASPLOOP|KLI_82_RASPLOOP"

PROCEDURE = "content.ImagingProcedure[0]"
# Series and BodyPosition are top-level content concepts; the procedure and the modality
# series only link to them by id (the connector reads them only from the top level). Each
# SPHN series class has its own content key. The helpers default to CT, so SERIES is the CT
# key; PLAIN_SERIES is for modalities without a class of their own (e.g. US).
SERIES_LINK = f"{PROCEDURE}.hasImagingSeries[0]"
SERIES = "content.ComputedTomographyImagingSeries[0]"
PLAIN_SERIES = "content.ImagingSeries[0]"
MR_SERIES = "content.MagneticResonanceImagingSeries[0]"
PET_SERIES = "content.PositronEmissionTomographyImagingSeries[0]"
XRAY_SERIES = "content.XRayImagingSeries[0]"
# SPHN series class per DICOM modality (from the hasImagingModalityCode restriction of
# each class); any other in-scope modality is a plain ImagingSeries.
XRAY_MODALITIES = ("BMD", "CR", "DX", "IO", "MG", "PX", "RF", "RG", "XA")
SERIES_CLASS = {
    "CT": "ComputedTomographyImagingSeries",
    "MR": "MagneticResonanceImagingSeries",
    "PT": "PositronEmissionTomographyImagingSeries",
    **{code: "XRayImagingSeries" for code in XRAY_MODALITIES},
}
SERIES_KEYS = (
    "ImagingSeries",
    "ComputedTomographyImagingSeries",
    "MagneticResonanceImagingSeries",
    "PositronEmissionTomographyImagingSeries",
    "XRayImagingSeries",
)
BODY_POSITION = "content.BodyPosition[0]"
BODY_POSITION_CODE = f"{BODY_POSITION}.hasCode"
SPHN = "https://biomedit.ch/rdf/sphn-schema/sphn#"

FRAME = f"{SERIES}.hasImagingFrame[0]"
MR_FRAME = f"{MR_SERIES}.hasImagingFrame[0]"
DIMENSIONS = f"{FRAME}.hasImageDimensions"
INDIVIDUAL = "https://biomedit.ch/rdf/sphn-schema/sphn/individual#"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"


def make_dicom_extension(tag, value, name=None):
    """Create one DICOM tag/value extension, as carried on ImagingStudy.series.

    The value type follows the export: int -> valueInteger, float -> valueDecimal,
    str -> valueString, and a list of (tag, value) pairs -> a code sequence, which
    the export flattens to one attribute per item.
    """
    nested = [{"url": "tag", "valueString": tag}]
    if name:
        nested.append({"url": "name", "valueString": name})
    if isinstance(value, list):
        nested.append(
            {
                "url": "sequence",
                "extension": [
                    {"url": "item", "extension": [make_dicom_extension(t, v)]}
                    for t, v in value
                ],
            }
        )
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        nested.append({"url": "value", "valueString": value})
    elif isinstance(value, int):
        nested.append({"url": "value", "valueInteger": value})
    else:
        nested.append({"url": "value", "valueDecimal": value})

    return {"url": DICOM_EXTENSION_URL, "extension": nested}


def code_sequence(code_value, scheme="SRT", meaning=None):
    """A one-item code sequence value: CodeValue, Coding Scheme Designator, Code Meaning."""
    items = [("00080100", code_value), ("00080102", scheme)]
    if meaning:
        items.append(("00080104", meaning))
    return items


def make_series(
    uid="series-1",
    modality="CT",
    number_of_instances=None,
    started=None,
    description=None,
    patient_position=None,
    extensions=None,
    instances=None,
):
    """Create an ImagingStudy.series entry (series.modality is a single Coding).

    instances is a list of instance uids; the Balgrist export lists one per series.
    """
    series = {
        "uid": uid,
        "modality": {"system": DICOM_SYSTEM, "code": modality},
    }

    if instances:
        series["instance"] = [
            {
                "uid": instance_uid,
                "sopClass": {"system": DICOM_SYSTEM, "code": SECONDARY_CAPTURE},
                "number": number,
            }
            for number, instance_uid in enumerate(instances, start=1)
        ]

    if number_of_instances is not None:
        series["numberOfInstances"] = number_of_instances

    if started:
        series["started"] = started

    if description:
        series["description"] = description

    series_extensions = list(extensions) if extensions else []
    if patient_position:
        series_extensions.append(
            make_dicom_extension(
                PATIENT_POSITION_TAG, patient_position, "PatientPosition"
            )
        )
    if series_extensions:
        series["extension"] = series_extensions

    return series


def make_imaging_study(
    study_id="imaging-1",
    secondary_value="secondary-1",
    official_value="1.3.6.1.4.1.28841.1.223.1325890505.6104.1517491701.693",
    modality="CT",
    started="2012-01-11T12:03:00+01:00",
    series=None,
    subject_reference=SUBJECT_REFERENCE,
    source=DICOM_SOURCE,
):
    """Create an ImagingStudy resource (study.modality is an array of Coding).

    series=None gives one CT series, since the map skips studies without an
    in-scope series; pass series=[] for a study with no series at all.
    """
    if series is None:
        series = [make_series()]
    study = {
        "resourceType": "ImagingStudy",
        "id": study_id,
        "meta": {"source": source},
        "status": "available",
        "identifier": [],
        "subject": {"reference": subject_reference},
    }

    if official_value:
        study["identifier"].append(
            {"use": "official", "system": "urn:dicom:uid", "value": official_value}
        )

    if secondary_value:
        study["identifier"].append(
            {"use": "secondary", "system": "RASPLOOP", "value": secondary_value}
        )

    if modality:
        study["modality"] = [{"system": DICOM_SYSTEM, "code": modality}]

    if started:
        study["started"] = started

    if series:
        study["series"] = series

    return study


class TestImagingProcedureBasic:
    """Test basic ImagingProcedure creation."""

    def test_imaging_study_creates_imaging_procedure(
        self, transform_bundle, make_bundle, base_patient
    ):
        """ImagingStudy creates ImagingProcedure."""
        study = make_imaging_study()
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PROCEDURE)

    def test_procedure_id_from_secondary_identifier(
        self, transform_bundle, make_bundle, base_patient
    ):
        """id comes from the identifier with use = 'secondary', prefixed."""
        study = make_imaging_study(secondary_value="my-secondary")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingProcedure/my-secondary")

    def test_official_identifier_not_used_for_id(
        self, transform_bundle, make_bundle, base_patient
    ):
        """The official DICOM UID identifier is ignored for the id."""
        study = make_imaging_study(
            official_value="1.2.3.4.5", secondary_value="my-secondary"
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingProcedure/my-secondary")

    def test_procedure_id_falls_back_to_resource_id(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Without a secondary identifier the id comes from the resource id, so the
        procedure still has one (Furnace rejects concepts without an id)."""
        study = make_imaging_study(study_id="study-42", secondary_value=None)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingStudy/study-42")

    def test_secondary_identifier_takes_precedence_over_resource_id(
        self, transform_bundle, make_bundle, base_patient
    ):
        """With a secondary identifier the resource-id fallback is not applied."""
        study = make_imaging_study(study_id="study-42", secondary_value="my-secondary")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingProcedure/my-secondary")

    def test_started_maps_to_start_date_time(
        self, transform_bundle, make_bundle, base_patient
    ):
        """started maps to hasStartDateTime."""
        study = make_imaging_study(started="2018-07-02T09:22:11+02:00")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{PROCEDURE}.hasStartDateTime", "2018-07-02T09:22:11+02:00"
        )

    def test_missing_started_skips_study(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study without started is not mapped (SPHN hasStartDateTime is 1..1),
        even when its series carry a started - there is no fallback to those."""
        study = make_imaging_study(
            started=None, series=[make_series(started="2012-01-11T12:18:56+01:00")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, PROCEDURE) is None


class TestSourceSystem:
    """Test meta.source -> hasSourceSystem (Utils.map refSourceSystem)."""

    def test_source_system_reference(self, transform_bundle, make_bundle, base_patient):
        """meta.source becomes a reference to the SourceSystem."""
        study = make_imaging_study()
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_reference(result, f"{PROCEDURE}.hasSourceSystem[0]", DICOM_SOURCE)

    def test_source_fragment_stripped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Any '#fragment' on meta.source is stripped from the reference."""
        study = make_imaging_study(source=f"{DICOM_SOURCE}#4711")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_reference(result, f"{PROCEDURE}.hasSourceSystem[0]", DICOM_SOURCE)


class TestSubjectPseudoIdentifier:
    """No hasSubjectPseudoIdentifier anywhere in the imaging output.

    ImagingProcedure, the series and BodyPosition are all top-level content
    concepts, so the connector injects the subject itself. Its JSON schema has no
    such property on them and allows no extra ones, so an explicit one is rejected.
    """

    def test_no_subject_pseudo_identifier_on_procedure(
        self, transform_bundle, make_bundle, base_patient
    ):
        """No hasSubjectPseudoIdentifier on the procedure."""
        study = make_imaging_study()
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PROCEDURE)
        assert get_path(result, f"{PROCEDURE}.hasSubjectPseudoIdentifier") is None

    def test_no_subject_pseudo_identifier_on_series(
        self, transform_bundle, make_bundle, base_patient
    ):
        """No hasSubjectPseudoIdentifier on a top-level series."""
        bundle = make_bundle(base_patient, make_imaging_study())

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasSubjectPseudoIdentifier") is None

    def test_no_subject_pseudo_identifier_on_mr_series_and_body_position(
        self, transform_bundle, make_bundle, base_patient
    ):
        """No hasSubjectPseudoIdentifier on the MR series or its BodyPosition."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, MR_SERIES)
        assert_path_exists(result, BODY_POSITION)
        assert get_path(result, f"{MR_SERIES}.hasSubjectPseudoIdentifier") is None
        assert get_path(result, f"{BODY_POSITION}.hasSubjectPseudoIdentifier") is None


class TestAcquisitionModality:
    """Test modality -> hasCode via cm-acquisitionModality (DICOM -> SNOMED)."""

    def test_ct_maps_to_computed_tomography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """CT maps to SNOMED 77477000 (Computed tomography)."""
        study = make_imaging_study(modality="CT")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "77477000", "/77477000")

    def test_mr_maps_to_magnetic_resonance_imaging(
        self, transform_bundle, make_bundle, base_patient
    ):
        """MR maps to SNOMED 113091000 (Magnetic resonance imaging)."""
        study = make_imaging_study(modality="MR")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "113091000", "/113091000")

    def test_us_maps_to_medical_ultrasonography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """US maps to SNOMED 16310003 (Medical ultrasonography)."""
        study = make_imaging_study(modality="US")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "16310003", "/16310003")

    def test_xa_maps_to_angiography(self, transform_bundle, make_bundle, base_patient):
        """XA maps to SNOMED 77343006 (Angiography)."""
        study = make_imaging_study(modality="XA")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "77343006", "/77343006")

    def test_rf_maps_to_fluoroscopy(self, transform_bundle, make_bundle, base_patient):
        """RF maps to SNOMED 44491008 (Fluoroscopy)."""
        study = make_imaging_study(modality="RF")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "44491008", "/44491008")

    def test_dx_maps_to_plain_radiography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """DX maps to SNOMED 168537006 (Plain radiography)."""
        study = make_imaging_study(modality="DX")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "168537006", "/168537006")

    def test_cr_maps_to_plain_radiography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """CR shares the DX target, SNOMED 168537006 (Plain radiography)."""
        study = make_imaging_study(modality="CR")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "168537006", "/168537006")

    def test_pt_maps_to_positron_emission_tomography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A PET-only study maps to SNOMED 82918005 and gets its PET series."""
        study = make_imaging_study(modality="PT", series=[make_series(modality="PT")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "82918005", "/82918005")
        assert_path_exists(result, PET_SERIES)

    def test_mg_maps_to_mammography(self, transform_bundle, make_bundle, base_patient):
        """A mammography-only study maps to SNOMED 71651007 and gets its X-ray series."""
        study = make_imaging_study(modality="MG", series=[make_series(modality="MG")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PROCEDURE}.hasCode[0]", "71651007", "/71651007")
        assert_path_exists(result, XRAY_SERIES)

    def test_code_is_snomed_iri_list(self, transform_bundle, make_bundle, base_patient):
        """hasCode is a list of SPHN Codes whose iri is the full SNOMED id."""
        study = make_imaging_study(modality="CT")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{PROCEDURE}.hasCode", 1)
        assert_path_equals(
            result, f"{PROCEDURE}.hasCode[0].iri", f"{SNOMED_ID_SYSTEM}/77477000"
        )


class TestUnmappedModality:
    """Test modalities with no cm-acquisitionModality entry.

    OT, ES, SR and PR are omitted from the concept map on purpose (map lines
    13-15): they are not imaging acquisition procedures, so there is no valid
    descendant of SNOMED 363679005 to map them to. Without a code the study is
    empty for SPHN (hasCode is required), so it is not mapped at all.
    """

    def test_ot_study_is_skipped(self, transform_bundle, make_bundle, base_patient):
        """An OT study is not mapped, even with an in-scope (CT) series."""
        study = make_imaging_study(modality="OT", series=[make_series(modality="CT")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, PROCEDURE) is None

    def test_missing_modality_study_is_skipped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study without modality is not mapped."""
        study = make_imaging_study(modality=None)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, PROCEDURE) is None


class TestImagingSeries:
    """Test series -> hasImagingSeries."""

    def test_series_creates_imaging_series(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A series creates an ImagingSeries."""
        study = make_imaging_study(series=[make_series()])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)

    def test_series_id_prefixed(self, transform_bundle, make_bundle, base_patient):
        """ImagingSeries id is the series uid prefixed with 'ImagingSeries/'."""
        study = make_imaging_study(series=[make_series(uid="my-series-uid")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{SERIES}.id", "ImagingSeries/my-series-uid")

    def test_series_description(self, transform_bundle, make_bundle, base_patient):
        """series.description maps to hasDescription."""
        study = make_imaging_study(series=[make_series(description="Test description")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{SERIES}.hasDescription", "Test description")

    def test_series_started(self, transform_bundle, make_bundle, base_patient):
        """series.started maps to hasStartDateTime."""
        study = make_imaging_study(
            series=[make_series(started="2012-01-11T12:18:56+01:00")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{SERIES}.hasStartDateTime", "2012-01-11T12:18:56+01:00"
        )

    def test_series_modality_code(self, transform_bundle, make_bundle, base_patient):
        """series.modality is kept as a dcm: code (iri + termid), not translated."""
        study = make_imaging_study(series=[make_series(modality="US")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{PLAIN_SERIES}.hasImagingModalityCode", "US")
        assert_path_equals(
            result, f"{PLAIN_SERIES}.hasImagingModalityCode.iri", f"{DICOM_SYSTEM}/US"
        )

    def test_mr_series_modality_code(self, transform_bundle, make_bundle, base_patient):
        """An MR series carries dcm:MR, the code SPHN pins MR series to."""
        study = make_imaging_study(modality="MR", series=[make_series(modality="MR")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{MR_SERIES}.hasImagingModalityCode", "MR", "/DCM/MR")

    def test_series_modality_not_in_concept_map_keeps_code(
        self, transform_bundle, make_bundle, base_patient
    ):
        """NM has no cm-acquisitionModality entry but is an allowed DCM series code."""
        study = make_imaging_study(series=[make_series(modality="NM")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, f"{PLAIN_SERIES}.hasImagingModalityCode", "NM", "/DCM/NM"
        )

    def test_series_source_system(self, transform_bundle, make_bundle, base_patient):
        """Every series, MR or not, takes the study's meta.source (SPHN: 1..*)."""
        study = make_imaging_study(
            source=f"{DICOM_SOURCE}#4711",
            series=[
                make_series(uid="series-ct", modality="CT"),
                make_series(uid="series-mr", modality="MR"),
            ],
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        for series in (SERIES, MR_SERIES):
            assert_reference(result, f"{series}.hasSourceSystem[0]", DICOM_SOURCE)

    def test_only_out_of_scope_series_skips_study(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study whose series are all out of scope (SR) would be empty, so it is
        not mapped at all."""
        study = make_imaging_study(series=[make_series(modality="SR")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, PROCEDURE) is None

    def test_out_of_scope_series_leaves_others(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Only the out-of-scope series (OT, PR) are dropped from a mixed study."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-ct", modality="CT"),
                make_series(uid="series-ot", modality="OT"),
                make_series(uid="series-pr", modality="PR"),
                make_series(uid="series-mr", modality="MR"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series_list = get_path(result, f"{PROCEDURE}.hasImagingSeries")
        assert {s.get("id") for s in series_list} == {
            "ImagingSeries/series-ct",
            "ImagingSeries/series-mr",
        }

    def test_multiple_series(self, transform_bundle, make_bundle, base_patient):
        """Each series creates its own ImagingSeries."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-a"),
                make_series(uid="series-b"),
                make_series(uid="series-c"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{PROCEDURE}.hasImagingSeries", 3)
        assert_list_length(result, "content.ComputedTomographyImagingSeries", 3)

    def test_series_are_top_level_not_nested(
        self, transform_bundle, make_bundle, base_patient
    ):
        """The procedure only links to the series ({id, target_concept}); the series
        content is a top-level concept, the only place the connector reads it from."""
        study = make_imaging_study(series=[make_series(uid="series-a", description="desc")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, SERIES_LINK) == {
            "id": "ImagingSeries/series-a",
            "target_concept": f"{SPHN}ComputedTomographyImagingSeries",
        }
        assert_path_equals(result, f"{SERIES}.id", "ImagingSeries/series-a")
        assert_path_equals(result, f"{SERIES}.hasDescription", "desc")

    def test_every_link_matches_a_top_level_series(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Each link id is the id of a series under the content key its target_concept
        names, so the connector's IRI for the link and for the series are the same."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-ct", modality="CT"),
                make_series(uid="series-mr", modality="MR"),
                make_series(uid="series-pt", modality="PT"),
                make_series(uid="series-dx", modality="DX"),
                make_series(uid="series-us", modality="US"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        links = get_path(result, f"{PROCEDURE}.hasImagingSeries")
        assert len(links) == 5
        for link in links:
            # The content key is the SPHN class name that target_concept names.
            key = link["target_concept"].removeprefix(SPHN)
            series = get_path(result, f"content.{key}")
            assert link["id"] in {s["id"] for s in series}
        # Each series appears exactly once, under one key.
        all_ids = [
            s["id"] for key in SERIES_KEYS for s in (get_path(result, f"content.{key}") or [])
        ]
        assert sorted(all_ids) == sorted(link["id"] for link in links)

    def test_series_without_uid_is_skipped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A series without uid has no id to link by, so it is skipped."""
        no_uid = make_series(uid="series-x")
        del no_uid["uid"]
        study = make_imaging_study(series=[make_series(uid="series-a"), no_uid])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{PROCEDURE}.hasImagingSeries", 1)
        assert_list_length(result, "content.ComputedTomographyImagingSeries", 1)


class TestNumberOfFrames:
    """Test series.numberOfInstances -> hasNumberOfFrames (Utils.map imaging_unit_number)."""

    def test_number_of_instances_maps_to_number_of_frames(
        self, transform_bundle, make_bundle, base_patient
    ):
        """numberOfInstances becomes a Quantity with the UCUM count unit."""
        study = make_imaging_study(series=[make_series(number_of_instances=17)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_quantity_mapped(result, f"{SERIES}.hasNumberOfFrames", 17, "cblnbcbr")

    def test_number_of_frames_unit_iri(
        self, transform_bundle, make_bundle, base_patient
    ):
        """The count unit carries the SPHN UCUM iri."""
        study = make_imaging_study(series=[make_series(number_of_instances=4)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            f"{SERIES}.hasNumberOfFrames.hasUnit.hasCode.iri",
            "https://biomedit.ch/rdf/sphn-resource/ucum/cblnbcbr",
        )

    def test_missing_number_of_instances_omits_frames(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A series without numberOfInstances gets no hasNumberOfFrames."""
        study = make_imaging_study(series=[make_series(number_of_instances=None)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasNumberOfFrames") is None


class TestSeriesTargetConcept:
    """Test target_concept on the ImagingProcedure -> series links.

    hasImagingSeries ranges over ImagingSeries and its four modality classes, so
    the connector requires target_concept on every link and builds the series IRI
    from it. The series themselves carry none (not allowed there); their class is
    the content key they are put under.
    """

    def test_mr_series_link_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """An MR series is linked as MagneticResonanceImagingSeries and put under
        that content key."""
        study = make_imaging_study(modality="MR", series=[make_series(modality="MR")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{SERIES_LINK}.target_concept", f"{SPHN}MagneticResonanceImagingSeries"
        )
        assert_path_exists(result, MR_SERIES)
        assert get_path(result, SERIES) is None

    @pytest.mark.parametrize("modality", ["CT", "PT", *XRAY_MODALITIES])
    def test_modality_series_link_target_concept(
        self, modality, transform_bundle, make_bundle, base_patient
    ):
        """CT, PET and every X-ray modality go to their own SPHN class: the link's
        target_concept and the content key both name it, and no other key is used."""
        study = make_imaging_study(series=[make_series(modality=modality)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series_class = SERIES_CLASS[modality]
        assert_path_equals(result, f"{SERIES_LINK}.target_concept", f"{SPHN}{series_class}")
        assert_list_length(result, f"content.{series_class}", 1)
        for key in SERIES_KEYS:
            if key != series_class:
                assert get_path(result, f"content.{key}") is None

    @pytest.mark.parametrize("modality", ["US", "NM", "ES"])
    def test_plain_series_link_target_concept(
        self, modality, transform_bundle, make_bundle, base_patient
    ):
        """A modality without a class of its own (SPHN has no US class) is linked as
        plain ImagingSeries (target_concept is required on every link)."""
        study = make_imaging_study(series=[make_series(modality=modality)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{SERIES_LINK}.target_concept", f"{SPHN}ImagingSeries")
        assert_list_length(result, "content.ImagingSeries", 1)
        for key in SERIES_KEYS[1:]:
            assert get_path(result, f"content.{key}") is None

    def test_series_carry_no_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """No top-level series carries target_concept itself."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-mr", modality="MR"),
                make_series(uid="series-ct", modality="CT"),
                make_series(uid="series-pt", modality="PT"),
                make_series(uid="series-dx", modality="DX"),
                make_series(uid="series-us", modality="US"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        for series in (SERIES, MR_SERIES, PET_SERIES, XRAY_SERIES, PLAIN_SERIES):
            assert "target_concept" not in get_path(result, series)

    def test_mixed_series_get_distinct_target_concepts(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Series of different classes in one study each take their own rule exactly
        once."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-mr", modality="MR"),
                make_series(uid="series-ct", modality="CT"),
                make_series(uid="series-pt", modality="PT"),
                make_series(uid="series-xa", modality="XA"),
                make_series(uid="series-us", modality="US"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{PROCEDURE}.hasImagingSeries", 5)
        series_list = get_path(result, f"{PROCEDURE}.hasImagingSeries")
        by_id = {s.get("id"): s.get("target_concept") for s in series_list}
        assert by_id == {
            "ImagingSeries/series-mr": f"{SPHN}MagneticResonanceImagingSeries",
            "ImagingSeries/series-ct": f"{SPHN}ComputedTomographyImagingSeries",
            "ImagingSeries/series-pt": f"{SPHN}PositronEmissionTomographyImagingSeries",
            "ImagingSeries/series-xa": f"{SPHN}XRayImagingSeries",
            "ImagingSeries/series-us": f"{SPHN}ImagingSeries",
        }
        for key in SERIES_KEYS:
            assert_list_length(result, f"content.{key}", 1)


class TestBodyPosition:
    """Test DICOM Patient Position (0018,5100) -> BodyPosition.hasCode.

    The head-first / feet-first half of the DICOM term is table direction, not
    body position, and SPHN has no slot for it (hasCode is 1..1), so each pair
    collapses onto a single SNOMED body position code. BodyPosition.hasCode uses
    the iri + termid shape: SPHN's union there has no sphn:Code, so the
    hasCodingSystemAndVersion + hasIdentifier shape is rejected.
    """

    def test_hfs_maps_to_supine(self, transform_bundle, make_bundle, base_patient):
        """HFS (head first-supine) maps to SNOMED 40199007 (Supine body position)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, BODY_POSITION_CODE, "40199007", f"{SNOMED_ID_SYSTEM}/40199007"
        )
        code = get_path(result, BODY_POSITION_CODE)
        assert "hasCodingSystemAndVersion" not in code
        assert "hasIdentifier" not in code

    def test_body_position_source_system(
        self, transform_bundle, make_bundle, base_patient
    ):
        """BodyPosition takes the study's meta.source (SPHN requires it, 1..*)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_reference(result, f"{BODY_POSITION}.hasSourceSystem[0]", DICOM_SOURCE)

    def test_body_position_is_top_level_and_linked(
        self, transform_bundle, make_bundle, base_patient
    ):
        """BodyPosition is a top-level concept; the MR series links to it by id only.
        The id derives from the series uid, so it is stable across runs."""
        study = make_imaging_study(
            modality="MR",
            series=[make_series(uid="series-1", modality="MR", patient_position="HFS")],
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, f"{MR_SERIES}.hasBodyPosition") == [
            {"id": "BodyPosition/series-1"}
        ]
        assert_path_equals(result, f"{BODY_POSITION}.id", "BodyPosition/series-1")

    def test_body_position_has_unique_id(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Each BodyPosition carries its own id, matched by its series' link."""
        study = make_imaging_study(
            modality="MR",
            series=[
                make_series(uid="series-1", modality="MR", patient_position="HFS"),
                make_series(uid="series-2", modality="MR", patient_position="HFS"),
            ],
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series = get_path(result, "content.MagneticResonanceImagingSeries")
        links = [s["hasBodyPosition"][0]["id"] for s in series]
        ids = [b["id"] for b in get_path(result, "content.BodyPosition")]
        assert len(set(ids)) == 2
        assert sorted(links) == sorted(ids)

    def test_ffs_maps_to_supine(self, transform_bundle, make_bundle, base_patient):
        """FFS (feet first-supine) collapses onto the same code as HFS."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "40199007")

    def test_hfp_maps_to_prone(self, transform_bundle, make_bundle, base_patient):
        """HFP (head first-prone) maps to SNOMED 1240000 (Prone body position)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFP")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "1240000")

    def test_ffp_maps_to_prone(self, transform_bundle, make_bundle, base_patient):
        """FFP (feet first-prone) collapses onto the same code as HFP."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFP")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "1240000")

    def test_hfdr_maps_to_right_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """HFDR maps to SNOMED 102535000 (Right lateral decubitus)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFDR")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "102535000")

    def test_ffdr_maps_to_right_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """FFDR collapses onto the same code as HFDR."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFDR")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "102535000")

    def test_hfdl_maps_to_left_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """HFDL maps to SNOMED 102536004 (Left lateral decubitus)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFDL")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "102536004")

    def test_ffdl_maps_to_left_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """FFDL collapses onto the same code as HFDL."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFDL")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, BODY_POSITION_CODE, "102536004")


    @pytest.mark.parametrize("modality", ["CT", "PT", "DX"])
    def test_modality_series_get_body_position(
        self, modality, transform_bundle, make_bundle, base_patient
    ):
        """CT, PET and X-ray series get a BodyPosition like MR: a top-level concept the
        series links to by id, with the same code mapping."""
        study = make_imaging_study(
            series=[make_series(uid="series-1", modality=modality, patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series = f"content.{SERIES_CLASS[modality]}[0]"
        assert get_path(result, f"{series}.hasBodyPosition") == [
            {"id": "BodyPosition/series-1"}
        ]
        assert_list_length(result, "content.BodyPosition", 1)
        assert_path_equals(result, f"{BODY_POSITION}.id", "BodyPosition/series-1")
        assert_code_mapped(result, BODY_POSITION_CODE, "40199007", "/40199007")
        assert_reference(result, f"{BODY_POSITION}.hasSourceSystem[0]", DICOM_SOURCE)

    def test_every_body_position_link_resolves(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Across classes, each hasBodyPosition link matches exactly one top-level
        BodyPosition and no BodyPosition is left unlinked."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-mr", modality="MR", patient_position="HFP"),
                make_series(uid="series-ct", modality="CT", patient_position="HFS"),
                make_series(uid="series-ct2", modality="CT"),
                make_series(uid="series-us", modality="US", patient_position="HFS"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        links = [
            link["id"]
            for key in SERIES_KEYS
            for series in (get_path(result, f"content.{key}") or [])
            for link in series.get("hasBodyPosition", [])
        ]
        ids = [bp["id"] for bp in get_path(result, "content.BodyPosition")]
        assert sorted(links) == sorted(ids) == [
            "BodyPosition/series-ct",
            "BodyPosition/series-mr",
        ]


class TestBodyPositionGuards:
    """Test when BodyPosition is deliberately not created.

    Only the modality-class rules (CT, MR, PET, X-ray) link a BodyPosition (SPHN
    defines hasBodyPosition on the modality series, not on plain ImagingSeries), and
    it is guarded on a 0018,5100 value that cm-patientPosition can translate, so
    that a BodyPosition without hasCode - which SHACL rejects - is never emitted.
    """

    def test_mr_series_without_dicom_extension(
        self, transform_bundle, make_bundle, base_patient
    ):
        """An MR series with no DICOM extension gets no BodyPosition."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position=None)]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, MR_SERIES)
        assert get_path(result, f"{MR_SERIES}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None

    def test_mr_series_with_unrelated_tag(
        self, transform_bundle, make_bundle, base_patient
    ):
        """An MR series carrying only another DICOM tag gets no BodyPosition."""
        study = make_imaging_study(
            modality="MR",
            series=[
                make_series(
                    modality="MR",
                    extensions=[
                        make_dicom_extension("00185101", "AP", "ViewPosition")
                    ],
                )
            ],
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, MR_SERIES)
        assert get_path(result, f"{MR_SERIES}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None

    @pytest.mark.parametrize("modality", ["MR", "CT"])
    @pytest.mark.parametrize("position", ["LFP", "HFS FFS", "hfs"])
    def test_unmapped_patient_position(
        self, modality, position, transform_bundle, make_bundle, base_patient
    ):
        """A Patient Position the concept map cannot translate creates no BodyPosition
        (and no link): it would have no hasCode, which SHACL rejects."""
        study = make_imaging_study(
            modality=modality,
            series=[make_series(modality=modality, patient_position=position)],
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series = f"content.{SERIES_CLASS[modality]}[0]"
        assert_path_exists(result, series)
        assert get_path(result, f"{series}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None

    def test_patient_position_without_value(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A Patient Position tag with no value creates no BodyPosition."""
        extension = make_dicom_extension(PATIENT_POSITION_TAG, "HFS", "PatientPosition")
        extension["extension"] = [e for e in extension["extension"] if e["url"] != "value"]
        study = make_imaging_study(series=[make_series(extensions=[extension])])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None

    def test_mixed_valid_and_unmapped_positions(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Only the series with a translatable position get a BodyPosition."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-ok", modality="CT", patient_position="FFS"),
                make_series(uid="series-bad", modality="CT", patient_position="LFP"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        ids = [bp["id"] for bp in get_path(result, "content.BodyPosition")]
        assert ids == ["BodyPosition/series-ok"]
        linked = [
            link["id"]
            for series in get_path(result, "content.ComputedTomographyImagingSeries")
            for link in series.get("hasBodyPosition", [])
        ]
        assert linked == ids

    def test_plain_series_with_patient_position(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A plain ImagingSeries (e.g. US) drops the patient position: SPHN's
        ImagingSeries has no hasBodyPosition."""
        study = make_imaging_study(
            modality="US", series=[make_series(modality="US", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PLAIN_SERIES)
        assert get_path(result, f"{PLAIN_SERIES}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None

    @pytest.mark.parametrize("modality", ["CT", "PT", "DX"])
    def test_modality_series_without_patient_position(
        self, modality, transform_bundle, make_bundle, base_patient
    ):
        """The guard applies to CT, PET and X-ray as well: no tag, no BodyPosition."""
        study = make_imaging_study(series=[make_series(modality=modality)])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        series = f"content.{SERIES_CLASS[modality]}[0]"
        assert_path_exists(result, series)
        assert get_path(result, f"{series}.hasBodyPosition") is None
        assert get_path(result, "content.BodyPosition") is None


class TestMultipleStudies:
    """Test several ImagingStudy resources in one bundle."""

    def test_two_studies_create_two_procedures(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Each ImagingStudy creates its own ImagingProcedure."""
        first = make_imaging_study(study_id="imaging-1", secondary_value="first")
        second = make_imaging_study(study_id="imaging-2", secondary_value="second")
        bundle = make_bundle(base_patient, first, second)

        result = transform_bundle(bundle)

        assert_list_length(result, "content.ImagingProcedure", 2)
        procedures = get_path(result, "content.ImagingProcedure")
        assert {p.get("id") for p in procedures} == {
            "ImagingProcedure/first",
            "ImagingProcedure/second",
        }

    def test_study_without_series_is_skipped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study with no series at all is empty and not mapped."""
        study = make_imaging_study(series=[])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert get_path(result, PROCEDURE) is None

    def test_empty_study_leaves_others(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Skipping an empty study does not affect a complete one in the bundle."""
        empty = make_imaging_study(
            study_id="imaging-ot",
            secondary_value="ot",
            modality="OT",
            started=None,
            series=[make_series(modality="OT")],
        )
        kept = make_imaging_study(study_id="imaging-ct", secondary_value="ct")
        bundle = make_bundle(base_patient, empty, kept)

        result = transform_bundle(bundle)

        assert_list_length(result, "content.ImagingProcedure", 1)
        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingProcedure/ct")


def make_frame_study(*tags, modality="CT", instances=("instance-1",), **study_kwargs):
    """Create a study with one series listing the given instances.

    tags are (tag, value) pairs set as DICOM extensions on the series.
    """
    extensions = [make_dicom_extension(tag, value) for tag, value in tags]
    series = make_series(
        modality=modality, extensions=extensions, instances=list(instances)
    )
    return make_imaging_study(modality=modality, series=[series], **study_kwargs)


def frame_type_iris(result):
    return [t["iri"] for t in get_path(result, f"{FRAME}.hasType") or []]


class TestImagingFrame:
    """Test series.instance -> hasImagingFrame (frames stay nested in their series)."""

    def test_instance_creates_frame(self, transform_bundle, make_bundle, base_patient):
        """Each listed instance becomes a frame with an id from its uid."""
        bundle = make_bundle(base_patient, make_frame_study())

        result = transform_bundle(bundle)

        assert_list_length(result, f"{SERIES}.hasImagingFrame", 1)
        assert_path_equals(result, f"{FRAME}.id", "ImagingFrame/instance-1")

    def test_series_without_instance_has_no_frame(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A series that lists no instance gets no frame."""
        bundle = make_bundle(base_patient, make_imaging_study())

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasImagingFrame") is None

    def test_mr_frame_nested_without_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A frame of an MR series is nested in the MR series and carries no
        target_concept: each series class allows one frame class, which the connector
        derives from the series (its schema allows no target_concept on frames)."""
        bundle = make_bundle(base_patient, make_frame_study(modality="MR"))

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{MR_FRAME}.id", "ImagingFrame/instance-1")
        assert "target_concept" not in get_path(result, MR_FRAME)

    def test_non_mr_frame_has_no_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A frame of a non-MR series carries no target_concept either."""
        bundle = make_bundle(base_patient, make_frame_study(modality="CT"))

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert "target_concept" not in get_path(result, FRAME)

    @pytest.mark.parametrize("modality", ["PT", "DX"])
    def test_pet_and_xray_frames_nested_without_target_concept(
        self, modality, transform_bundle, make_bundle, base_patient
    ):
        """PET and X-ray frames are nested in their own series class, with the same
        frame mapping and no target_concept."""
        study = make_frame_study(("00080008", "ORIGINAL|PRIMARY"), modality=modality)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        frame = f"content.{SERIES_CLASS[modality]}[0].hasImagingFrame[0]"
        assert_path_equals(result, f"{frame}.id", "ImagingFrame/instance-1")
        assert "target_concept" not in get_path(result, frame)
        assert_path_exists(result, f"{frame}.hasType")

    def test_multiple_instances_carry_only_ids(
        self, transform_bundle, make_bundle, base_patient
    ):
        """With several instances the series header cannot be attributed to a frame."""
        study = make_frame_study(
            ("00080008", "ORIGINAL|PRIMARY"),
            ("0008002A", "20171123165915+0100"),
            instances=("instance-1", "instance-2"),
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        frames = get_path(result, f"{SERIES}.hasImagingFrame")
        assert [f["id"] for f in frames] == [
            "ImagingFrame/instance-1",
            "ImagingFrame/instance-2",
        ]
        for frame in frames:
            assert "hasType" not in frame
            assert "hasStartDateTime" not in frame


class TestImagingFrameType:
    """Test Image Type (0008,0008) values 1-3 -> hasType (cm-imagingFrameType)."""

    def test_three_values_map_to_individuals(
        self, transform_bundle, make_bundle, base_patient
    ):
        """ORIGINAL|PRIMARY|AXIAL maps to the three SPHN individuals, in order."""
        study = make_frame_study(("00080008", "ORIGINAL|PRIMARY|AXIAL"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert frame_type_iris(result) == [
            INDIVIDUAL + "Original",
            INDIVIDUAL + "Primary",
            INDIVIDUAL + "Axial",
        ]

    def test_single_value(self, transform_bundle, make_bundle, base_patient):
        """A one-value Image Type maps to one individual."""
        study = make_frame_study(("00080008", "DERIVED"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert frame_type_iris(result) == [INDIVIDUAL + "Derived"]

    def test_multi_word_value_is_normalized(
        self, transform_bundle, make_bundle, base_patient
    ):
        """SINGLE PLANE (with a space) maps to SinglePlane."""
        study = make_frame_study(("00080008", "DERIVED|SECONDARY|SINGLE PLANE"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert INDIVIDUAL + "SinglePlane" in frame_type_iris(result)

    def test_underscore_value_is_normalized(
        self, transform_bundle, make_bundle, base_patient
    ):
        """SMALL_PARTS (with an underscore) maps to SmallParts."""
        study = make_frame_study(("00080008", "ORIGINAL|PRIMARY|SMALL_PARTS"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert INDIVIDUAL + "SmallParts" in frame_type_iris(result)

    def test_empty_and_unknown_values_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """An empty value 3 and a value outside the SPHN set are dropped."""
        study = make_frame_study(("00080008", "ORIGINAL|M||RAD"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert frame_type_iris(result) == [INDIVIDUAL + "Original"]

    def test_values_after_third_not_mapped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Value 4+ is vendor-specific, even when it spells an SPHN name."""
        study = make_frame_study(("00080008", "ORIGINAL|PRIMARY|AXIAL|DERIVED|PARALLEL"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert frame_type_iris(result) == [
            INDIVIDUAL + "Original",
            INDIVIDUAL + "Primary",
            INDIVIDUAL + "Axial",
        ]

    def test_no_image_type(self, transform_bundle, make_bundle, base_patient):
        """Without Image Type the frame has no hasType."""
        bundle = make_bundle(base_patient, make_frame_study())

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasType") is None


class TestImagingFrameContentQualification:
    """Test Content Qualification (0018,9004) -> hasContentQualification."""

    def test_product(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00189004", "PRODUCT"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasContentQualification.iri", INDIVIDUAL + "Product"
        )

    def test_research(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00189004", "RESEARCH"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasContentQualification.iri", INDIVIDUAL + "Research"
        )

    def test_unknown_value_dropped(self, transform_bundle, make_bundle, base_patient):
        """A value that is not a DICOM defined term is not mapped."""
        study = make_frame_study(("00189004", "OTHER"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasContentQualification") is None


class TestImagingFrameStartDateTime:
    """Test Acquisition DateTime, or Acquisition Date + Time -> hasStartDateTime.

    DICOM times are local; without an offset of their own they take the
    study's (make_imaging_study defaults started to +01:00).
    """

    def test_acquisition_datetime_with_offset(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("0008002A", "20171123165915+0100"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasStartDateTime", "2017-11-23T16:59:15+01:00"
        )

    def test_acquisition_datetime_takes_study_offset(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A fractional DT without offset keeps its fraction and gets the study offset."""
        study = make_frame_study(
            ("0008002A", "20190620105023.307500"),
            started="2019-06-20T10:45:00+02:00",
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasStartDateTime", "2019-06-20T10:50:23.307500+02:00"
        )

    def test_acquisition_date_and_time(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00080022", "20171123"), ("00080032", "154923"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasStartDateTime", "2017-11-23T15:49:23+01:00"
        )

    def test_acquisition_datetime_preferred(
        self, transform_bundle, make_bundle, base_patient
    ):
        """With both, Acquisition DateTime wins and only one value is mapped."""
        study = make_frame_study(
            ("00080022", "20171123"),
            ("00080032", "154923"),
            ("0008002A", "20171123165915+0100"),
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasStartDateTime", "2017-11-23T16:59:15+01:00"
        )

    def test_partial_time_skipped(self, transform_bundle, make_bundle, base_patient):
        """A time without seconds is too imprecise for a dateTime and is skipped."""
        study = make_frame_study(("00080022", "20171123"), ("00080032", "1549"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasStartDateTime") is None

    def test_date_without_time_skipped(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00080022", "20171123"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasStartDateTime") is None


class TestImageDimensions:
    """Test Rows, Columns, Slice Thickness / Spacing and Pixel Spacing -> hasImageDimensions."""

    def test_rows_and_columns_are_counts(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00280010", 512), ("00280011", 1024))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_quantity_mapped(result, f"{DIMENSIONS}.hasNumberOfRows", 512, "cblnbcbr")
        assert_quantity_mapped(
            result, f"{DIMENSIONS}.hasNumberOfColumns", 1024, "cblnbcbr"
        )

    def test_slice_thickness_and_spacing_in_mm(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00180050", 0.6), ("00180088", 3.84))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_quantity_mapped(result, f"{DIMENSIONS}.hasSliceThickness", 0.6, "mm")
        assert_quantity_mapped(result, f"{DIMENSIONS}.hasSliceSpacing", 3.84, "mm")

    def test_pixel_spacing_row_then_column(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Pixel Spacing value 1 is the row spacing, value 2 the column spacing."""
        study = make_frame_study(("00280030", "0.5|0.25"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_quantity_mapped(
            result, f"{DIMENSIONS}.hasPixelDimensions.hasRowSpacing", 0.5, "mm"
        )
        assert_quantity_mapped(
            result, f"{DIMENSIONS}.hasPixelDimensions.hasColumnSpacing", 0.25, "mm"
        )

    def test_zero_slice_thickness_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A thickness of 0 is dropped, and alone it creates no ImageDimensions."""
        study = make_frame_study(("00180050", 0.0))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, DIMENSIONS) is None

    def test_zero_thickness_beside_rows(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00280010", 512), ("00180050", 0.0))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_quantity_mapped(result, f"{DIMENSIONS}.hasNumberOfRows", 512)
        assert get_path(result, f"{DIMENSIONS}.hasSliceThickness") is None

    def test_malformed_pixel_spacing_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A Pixel Spacing without two numbers creates no ImageDimensions."""
        study = make_frame_study(("00280030", "0.5"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, DIMENSIONS) is None


class TestAnatomicalProjection:
    """Test View Code Sequence, else View Position -> hasAnatomicalProjection."""

    def test_view_code_legacy_id(self, transform_bundle, make_bundle, base_patient):
        """The legacy SRT id is translated to SNOMED CT (CID 4010)."""
        study = make_frame_study(
            ("00540220", code_sequence("R-10206", meaning="antero-posterior"))
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            f"{FRAME}.hasAnatomicalProjection.hasCode",
            "399348003",
            f"{SNOMED_ID_SYSTEM}/399348003",
        )

    def test_pre_2008_postero_anterior(
        self, transform_bundle, make_bundle, base_patient
    ):
        """SNM3 R-10214, the code PA had before R-40888, is mapped too."""
        study = make_frame_study(("00540220", code_sequence("R-10214", "SNM3")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, f"{FRAME}.hasAnatomicalProjection.hasCode", "272479007"
        )

    def test_view_code_sct_taken_as_is(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00540220", code_sequence("399198007", "SCT")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            f"{FRAME}.hasAnatomicalProjection.hasCode",
            "399198007",
            f"{SNOMED_ID_SYSTEM}/399198007",
        )

    def test_view_position_fallback(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00185101", "RL"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, f"{FRAME}.hasAnatomicalProjection.hasCode", "399198007"
        )

    def test_view_code_wins_over_view_position(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(
            ("00540220", code_sequence("R-10236")), ("00185101", "AP")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, f"{FRAME}.hasAnatomicalProjection.hasCode", "399173006"
        )

    def test_unmapped_view_code_blocks_view_position(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A View Code Sequence outside the map gives no projection at all."""
        study = make_frame_study(
            ("00540220", code_sequence("R-99999")), ("00185101", "AP")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasAnatomicalProjection") is None

    def test_oblique_view_position_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00185101", "LLO"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasAnatomicalProjection") is None


class TestFrameBodySite:
    """Test Anatomic Region Sequence (+ Image Laterality) -> hasBodySite."""

    def test_region_legacy_id(self, transform_bundle, make_bundle, base_patient):
        """The legacy SRT id is translated to SNOMED CT (CID 4031)."""
        study = make_frame_study(("00082218", code_sequence("T-D9400", meaning="Leg")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{FRAME}.hasBodySite", 1)
        assert_code_mapped(
            result,
            f"{FRAME}.hasBodySite[0].hasCode",
            "30021000",
            f"{SNOMED_ID_SYSTEM}/30021000",
        )

    def test_non_standard_spine_id(self, transform_bundle, make_bundle, base_patient):
        """T-D0146 (Spine), outside CID 4031, maps like T-D04FF."""
        study = make_frame_study(("00082218", code_sequence("T-D0146", meaning="Spine")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{FRAME}.hasBodySite[0].hasCode", "421060004")

    def test_region_sct_taken_as_is(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00082218", code_sequence("72696002", "SCT")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(result, f"{FRAME}.hasBodySite[0].hasCode", "72696002")

    def test_unmapped_region_dropped(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00082218", code_sequence("T-99999")))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasBodySite") is None

    def test_bilateral_laterality(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(
            ("00082218", code_sequence("T-26000", "SNM3")), ("00200062", "B")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            f"{FRAME}.hasBodySite[0].hasLaterality.hasCode",
            "51440002",
            f"{SNOMED_ID_SYSTEM}/51440002",
        )

    def test_left_laterality(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(
            ("00082218", code_sequence("T-D9200")), ("00200062", "L")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result, f"{FRAME}.hasBodySite[0].hasLaterality.hasCode", "7771000"
        )

    def test_unpaired_laterality_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        """U (unpaired body part) is not a laterality."""
        study = make_frame_study(
            ("00082218", code_sequence("T-D0010")), ("00200062", "U")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, f"{FRAME}.hasBodySite[0].hasCode")
        assert get_path(result, f"{FRAME}.hasBodySite[0].hasLaterality") is None

    def test_laterality_without_region(
        self, transform_bundle, make_bundle, base_patient
    ):
        """BodySite requires hasCode, so a laterality alone creates none."""
        study = make_frame_study(("00200062", "R"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasBodySite") is None


class TestDataCompressionAlgorithm:
    """Test Lossy Image Compression (+ ratio, method) -> hasAlgorithm."""

    def test_lossy_with_ratio_and_method(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(
            ("00282110", "01"), ("00282112", 13.793), ("00282114", "ISO_10918_1")
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{FRAME}.hasAlgorithm", 1)
        algorithm = f"{FRAME}.hasAlgorithm[0]"
        assert_path_equals(
            result, f"{algorithm}.hasType.iri", INDIVIDUAL + "LossyCompression"
        )
        assert_path_equals(result, f"{algorithm}.hasMethod.iri", INDIVIDUAL + "ISO109181")
        assert_quantity_mapped(result, f"{algorithm}.hasRatio", 13.793, "cblratiocbr")

    def test_two_digit_part_method(self, transform_bundle, make_bundle, base_patient):
        """ISO_14496_10 keeps all digits: ISO1449610."""
        study = make_frame_study(("00282110", "01"), ("00282114", "ISO_14496_10"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{FRAME}.hasAlgorithm[0].hasMethod.iri", INDIVIDUAL + "ISO1449610"
        )

    def test_unknown_method_dropped(self, transform_bundle, make_bundle, base_patient):
        study = make_frame_study(("00282110", "01"), ("00282114", "ISO_10918_1|ISO_14495_1"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, f"{FRAME}.hasAlgorithm[0].hasType")
        assert get_path(result, f"{FRAME}.hasAlgorithm[0].hasMethod") is None

    def test_never_lossy_compressed(self, transform_bundle, make_bundle, base_patient):
        """00 does not mean lossless compression, so no algorithm is created."""
        study = make_frame_study(("00282110", "00"), ("00282112", 1.0))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasAlgorithm") is None


class TestImagingMetric:
    """Test Rescale Type (0028,1054) -> hasImagingMetric."""

    def test_hounsfield_is_attenuation_coefficient(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00281054", "HU"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            f"{FRAME}.hasImagingMetric.hasTypeCode",
            "112031",
            f"{DICOM_SYSTEM}/112031",
        )
        assert get_path(result, f"{FRAME}.hasImagingMetric.hasUnit") is None

    def test_unspecified_rescale_type_dropped(
        self, transform_bundle, make_bundle, base_patient
    ):
        study = make_frame_study(("00281054", "US"))
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, FRAME)
        assert get_path(result, f"{FRAME}.hasImagingMetric") is None
