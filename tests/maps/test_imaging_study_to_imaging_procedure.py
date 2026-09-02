"""
Tests for ImagingStudyToImagingProcedure.map

Tests the ImagingStudy -> ImagingProcedure mapping including:
- identifier (use = secondary) -> id (prefixed 'ImagingProcedure/')
- meta.source                  -> hasSourceSystem
- started                      -> hasStartDateTime
- modality                     -> hasCode (cm-acquisitionModality, DICOM -> SNOMED)
- subject.reference            -> hasSubjectPseudoIdentifier
- series                       -> hasImagingSeries (uid, description, started,
                                  modality, numberOfInstances -> hasNumberOfFrames)
- series (MR only)             -> target_concept + hasBodyPosition from DICOM
                                  Patient Position (0018,5100), cm-patientPosition

Note on Code shapes: hasCode and hasImagingModalityCode are assigned a bare
translate() result (map lines 54 and 91), so they come out as a FHIR Coding
('system' + 'code') rather than the SPHN Code shape used everywhere else. That
satisfies neither branch of the code-iri-or-codingSystem invariant
(model/LogicalModel.fsh:8-11), so assert_code_mapped - which checks termid/iri -
is not usable on them. BodyPosition.hasCode does use a valid branch
(hasCodingSystemAndVersion + hasIdentifier), which assert_code_mapped also
cannot check. Both are asserted with plain paths below.
"""

from tests.helpers import (
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
SNOMED_SCT_SYSTEM = "http://snomed.info/sct"
PATIENT_POSITION_TAG = "00185100"
DICOM_SOURCE = "https://research.balgrist.ch/HDR/DICOM"
SUBJECT_REFERENCE = "Patient?identifier=RASPLOOP|KLI_82_RASPLOOP"

PROCEDURE = "content.ImagingProcedure[0]"
SERIES = "content.ImagingProcedure[0].hasImagingSeries[0]"
BODY_POSITION_CODE = "content.ImagingProcedure[0].hasImagingSeries[0].hasBodyPosition[0].hasCode"


def make_dicom_extension(tag, value, name=None):
    """Create one DICOM tag/value extension, as carried on ImagingStudy.series."""
    nested = [{"url": "tag", "valueString": tag}]
    if name:
        nested.append({"url": "name", "valueString": name})
    nested.append({"url": "value", "valueString": value})

    return {"url": DICOM_EXTENSION_URL, "extension": nested}


def make_series(
    uid="series-1",
    modality="CT",
    number_of_instances=None,
    started=None,
    description=None,
    patient_position=None,
    extensions=None,
):
    """Create an ImagingStudy.series entry (series.modality is a single Coding)."""
    series = {
        "uid": uid,
        "modality": {"system": DICOM_SYSTEM, "code": modality},
    }

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
    """Create an ImagingStudy resource (study.modality is an array of Coding)."""
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

    if series is not None:
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

    def test_missing_started_omits_start_date_time(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study without started still creates the procedure, without
        hasStartDateTime - even though SPHN declares it 1..1 on MedicalProcedure
        (model/LogicalModel.fsh:581)."""
        study = make_imaging_study(started=None)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PROCEDURE)
        assert get_path(result, f"{PROCEDURE}.hasStartDateTime") is None


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
    """Test subject.reference -> hasSubjectPseudoIdentifier."""

    def test_subject_pseudo_identifier_id(
        self, transform_bundle, make_bundle, base_patient
    ):
        """id joins the identifier system and value with '_'."""
        study = make_imaging_study()
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            f"{PROCEDURE}.hasSubjectPseudoIdentifier.id",
            "RASPLOOP_KLI_82_RASPLOOP",
        )

    def test_subject_pseudo_identifier_has_identifier(
        self, transform_bundle, make_bundle, base_patient
    ):
        """hasIdentifier keeps the '|' separator of the source reference."""
        study = make_imaging_study()
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            f"{PROCEDURE}.hasSubjectPseudoIdentifier.hasIdentifier",
            "RASPLOOP|KLI_82_RASPLOOP",
        )


class TestAcquisitionModality:
    """Test modality -> hasCode via cm-acquisitionModality (DICOM -> SNOMED)."""

    def test_ct_maps_to_computed_tomography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """CT maps to SNOMED 77477000 (Computed tomography)."""
        study = make_imaging_study(modality="CT")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "77477000")

    def test_mr_maps_to_magnetic_resonance_imaging(
        self, transform_bundle, make_bundle, base_patient
    ):
        """MR maps to SNOMED 113091000 (Magnetic resonance imaging)."""
        study = make_imaging_study(modality="MR")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "113091000")

    def test_us_maps_to_medical_ultrasonography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """US maps to SNOMED 16310003 (Medical ultrasonography)."""
        study = make_imaging_study(modality="US")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "16310003")

    def test_xa_maps_to_angiography(self, transform_bundle, make_bundle, base_patient):
        """XA maps to SNOMED 77343006 (Angiography)."""
        study = make_imaging_study(modality="XA")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "77343006")

    def test_rf_maps_to_fluoroscopy(self, transform_bundle, make_bundle, base_patient):
        """RF maps to SNOMED 44491008 (Fluoroscopy)."""
        study = make_imaging_study(modality="RF")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "44491008")

    def test_dx_maps_to_plain_radiography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """DX maps to SNOMED 168537006 (Plain radiography)."""
        study = make_imaging_study(modality="DX")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "168537006")

    def test_cr_maps_to_plain_radiography(
        self, transform_bundle, make_bundle, base_patient
    ):
        """CR shares the DX target, SNOMED 168537006 (Plain radiography)."""
        study = make_imaging_study(modality="CR")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.code", "168537006")

    def test_code_system_is_snomed(self, transform_bundle, make_bundle, base_patient):
        """The translated code carries the cm-acquisitionModality target system."""
        study = make_imaging_study(modality="CT")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.hasCode.system", SNOMED_ID_SYSTEM)


class TestUnmappedModality:
    """Test modalities with no cm-acquisitionModality entry.

    OT, ES, SR and PR are omitted from the concept map on purpose (map lines
    13-15): they are not imaging acquisition procedures, so there is no valid
    descendant of SNOMED 363679005 to map them to. The procedure is still
    emitted, without hasCode - although SPHN declares hasCode 1..1 on
    MedicalProcedure (model/LogicalModel.fsh:583).
    """

    def test_ot_yields_no_code(self, transform_bundle, make_bundle, base_patient):
        """An OT study is still mapped, but carries no hasCode."""
        study = make_imaging_study(modality="OT", secondary_value="ot-study")
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{PROCEDURE}.id", "ImagingProcedure/ot-study")
        assert get_path(result, f"{PROCEDURE}.hasCode") is None

    def test_missing_modality_yields_no_code(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A study without modality is still mapped, but carries no hasCode."""
        study = make_imaging_study(modality=None)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PROCEDURE)
        assert get_path(result, f"{PROCEDURE}.hasCode") is None


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
        """series.modality maps to hasImagingModalityCode via cm-acquisitionModality."""
        study = make_imaging_study(series=[make_series(modality="US")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{SERIES}.hasImagingModalityCode.code", "16310003")
        assert_path_equals(
            result, f"{SERIES}.hasImagingModalityCode.system", SNOMED_ID_SYSTEM
        )

    def test_unmapped_series_modality_omits_code(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A series whose modality has no concept map entry (SR) keeps no code."""
        study = make_imaging_study(series=[make_series(modality="SR")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasImagingModalityCode") is None

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
    """Test target_concept, which carries the real SPHN series class.

    The modality-specific SPHN series classes are flattened into
    SPHN-ImagingSeries (model/LogicalModel.fsh:628-639), so the MR and the
    default branch create the same type and differ only in target_concept.
    """

    def test_mr_series_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """An MR series is tagged as MagneticResonanceImagingSeries."""
        study = make_imaging_study(modality="MR", series=[make_series(modality="MR")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            f"{SERIES}.target_concept",
            "https://biomedit.ch/rdf/sphn-schema/sphn#MagneticResonanceImagingSeries",
        )

    def test_non_mr_series_target_concept(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A non-MR series is tagged as the base ImagingSeries."""
        study = make_imaging_study(series=[make_series(modality="CT")])
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            f"{SERIES}.target_concept",
            "https://biomedit.ch/rdf/sphn-schema/sphn#ImagingSeries",
        )

    def test_mixed_series_get_distinct_target_concepts(
        self, transform_bundle, make_bundle, base_patient
    ):
        """MR and non-MR series in one study each take their own branch exactly once."""
        study = make_imaging_study(
            series=[
                make_series(uid="series-mr", modality="MR"),
                make_series(uid="series-ct", modality="CT"),
            ]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_list_length(result, f"{PROCEDURE}.hasImagingSeries", 2)
        series_list = get_path(result, f"{PROCEDURE}.hasImagingSeries")
        by_id = {s.get("id"): s.get("target_concept") for s in series_list}
        assert by_id["ImagingSeries/series-mr"] == (
            "https://biomedit.ch/rdf/sphn-schema/sphn#MagneticResonanceImagingSeries"
        )
        assert by_id["ImagingSeries/series-ct"] == (
            "https://biomedit.ch/rdf/sphn-schema/sphn#ImagingSeries"
        )


class TestBodyPosition:
    """Test DICOM Patient Position (0018,5100) -> BodyPosition.hasCode.

    The head-first / feet-first half of the DICOM term is table direction, not
    body position, and SPHN has no slot for it (hasCode is 1..1), so each pair
    collapses onto a single SNOMED body position code. BodyPosition.hasCode uses
    the hasCodingSystemAndVersion + hasIdentifier branch of code-iri-or-codingSystem.
    """

    def test_hfs_maps_to_supine(self, transform_bundle, make_bundle, base_patient):
        """HFS (head first-supine) maps to SNOMED 40199007 (Supine body position)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(
            result, f"{BODY_POSITION_CODE}.hasCodingSystemAndVersion", SNOMED_SCT_SYSTEM
        )
        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "40199007")

    def test_ffs_maps_to_supine(self, transform_bundle, make_bundle, base_patient):
        """FFS (feet first-supine) collapses onto the same code as HFS."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "40199007")

    def test_hfp_maps_to_prone(self, transform_bundle, make_bundle, base_patient):
        """HFP (head first-prone) maps to SNOMED 1240000 (Prone body position)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFP")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "1240000")

    def test_ffp_maps_to_prone(self, transform_bundle, make_bundle, base_patient):
        """FFP (feet first-prone) collapses onto the same code as HFP."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFP")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "1240000")

    def test_hfdr_maps_to_right_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """HFDR maps to SNOMED 102535000 (Right lateral decubitus)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFDR")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "102535000")

    def test_ffdr_maps_to_right_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """FFDR collapses onto the same code as HFDR."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFDR")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "102535000")

    def test_hfdl_maps_to_left_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """HFDL maps to SNOMED 102536004 (Left lateral decubitus)."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="HFDL")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "102536004")

    def test_ffdl_maps_to_left_lateral_decubitus(
        self, transform_bundle, make_bundle, base_patient
    ):
        """FFDL collapses onto the same code as HFDL."""
        study = make_imaging_study(
            modality="MR", series=[make_series(modality="MR", patient_position="FFDL")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_equals(result, f"{BODY_POSITION_CODE}.hasIdentifier", "102536004")


class TestBodyPositionGuards:
    """Test when BodyPosition is deliberately not created.

    Only the MR branch carries hasBodyPosition, which is what the
    body-position-modality-only invariant permits (model/LogicalModel.fsh:636-639),
    and the MR branch is guarded on the 0018,5100 tag being present so that an
    empty BodyPosition - whose hasCode would satisfy neither branch of
    code-iri-or-codingSystem - is never emitted.
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

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasBodyPosition") is None

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

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasBodyPosition") is None

    def test_non_mr_series_with_patient_position(
        self, transform_bundle, make_bundle, base_patient
    ):
        """A non-MR series drops the patient position, since only MR carries it."""
        study = make_imaging_study(
            series=[make_series(modality="CT", patient_position="HFS")]
        )
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, SERIES)
        assert get_path(result, f"{SERIES}.hasBodyPosition") is None


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

    def test_study_without_series(self, transform_bundle, make_bundle, base_patient):
        """A study with no series creates a procedure with no ImagingSeries."""
        study = make_imaging_study(series=None)
        bundle = make_bundle(base_patient, study)

        result = transform_bundle(bundle)

        assert_path_exists(result, PROCEDURE)
        assert get_path(result, f"{PROCEDURE}.hasImagingSeries") is None
