"""
Tests for ClaimToBilledDiagnosisProcedure.map

Tests the Claim -> BilledDiagnosis and BilledProcedure mappings including:
- diagnosis -> BilledDiagnosis with ICD-10 code and rank
- procedure -> BilledProcedure with CHOP code and rank
- sequence -> hasRankCode (Principal vs Complementary/Supplementary)
"""

import pytest

from tests.helpers import (
    assert_code_mapped,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_claim(
    claim_id="claim-1",
    diagnoses=None,
    procedures=None,
    created=None,
    encounter_ref=None,
):
    """Create a Claim resource with diagnoses and procedures."""
    claim = {
        "resourceType": "Claim",
        "id": claim_id,
        "meta": {"source": "http://example.org/ehr"},
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "institutional",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": "Patient/pat-1"},
        "provider": {"reference": "Organization/org-1"},
        "priority": {"coding": [{"code": "normal"}]},
    }

    if created:
        claim["created"] = created

    if encounter_ref:
        claim["extension"] = [
            {
                "url": "http://research.balgrist.ch/fhir/StructureDefinition/encounter-id",
                "valueReference": {"reference": encounter_ref},
            }
        ]

    if diagnoses:
        claim["diagnosis"] = diagnoses

    if procedures:
        claim["procedure"] = procedures

    return claim


def make_diagnosis_entry(sequence, icd10_code):
    """Create a diagnosis entry for a Claim."""
    return {
        "sequence": sequence,
        "diagnosisCodeableConcept": {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": icd10_code}]
        },
    }


def make_procedure_entry(sequence, chop_code):
    """Create a procedure entry for a Claim."""
    return {
        "sequence": sequence,
        "procedureCodeableConcept": {
            "coding": [{"system": "http://www.bfs.admin.ch/chop", "code": chop_code}]
        },
    }


class TestBilledDiagnosisBasic:
    """Test basic BilledDiagnosis creation."""

    def test_claim_diagnosis_creates_billed_diagnosis(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Claim diagnosis creates BilledDiagnosis."""
        claim = make_claim(diagnoses=[make_diagnosis_entry(1, "I10.9")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BilledDiagnosis[0]")

    def test_billed_diagnosis_id_format(self, transform_bundle, make_bundle, base_patient):
        """BilledDiagnosis id combines Claim id and sequence."""
        claim = make_claim(
            claim_id="my-claim",
            diagnoses=[make_diagnosis_entry(1, "I10.9")],
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.BilledDiagnosis[0].id", "Claim/my-claim-1")


class TestBilledDiagnosisCode:
    """Test diagnosis ICD-10 code mapping."""

    def test_icd10_code_mapped(self, transform_bundle, make_bundle, base_patient):
        """ICD-10 diagnosis code is correctly mapped."""
        claim = make_claim(diagnoses=[make_diagnosis_entry(1, "J18.9")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.BilledDiagnosis[0].hasCode.termid", "J18.9")

    def test_icd10_iri_format(self, transform_bundle, make_bundle, base_patient):
        """ICD-10 IRI uses biomedit.ch format."""
        claim = make_claim(diagnoses=[make_diagnosis_entry(1, "J18.9")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        iri = get_path(result, "content.BilledDiagnosis[0].hasCode.iri")
        assert iri == "https://biomedit.ch/rdf/sphn-resource/icd-10-gm/J18.9"


class TestBilledDiagnosisRank:
    """Test diagnosis sequence -> rank code mapping."""

    def test_sequence_1_maps_to_principal(self, transform_bundle, make_bundle, base_patient):
        """Diagnosis sequence 1 maps to Principal (SNOMED 63161005)."""
        claim = make_claim(diagnoses=[make_diagnosis_entry(1, "I10.9")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.BilledDiagnosis[0].hasRankCode",
            "63161005",
            "/63161005",
        )

    def test_sequence_2_maps_to_complementary(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Diagnosis sequence > 1 maps to Complementary (SNOMED 1354479004)."""
        claim = make_claim(
            diagnoses=[
                make_diagnosis_entry(1, "I10.9"),
                make_diagnosis_entry(2, "E11.9"),
            ]
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        # Find the second diagnosis (ID format: Claim/{claim-id}-{sequence})
        diagnoses = get_path(result, "content.BilledDiagnosis")
        second_diag = next(d for d in diagnoses if d.get("id") == "Claim/claim-1-2")

        assert second_diag is not None
        assert second_diag["hasRankCode"]["termid"] == "1354479004"


class TestBilledProcedureBasic:
    """Test basic BilledProcedure creation."""

    def test_claim_procedure_creates_billed_procedure(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Claim procedure creates BilledProcedure."""
        claim = make_claim(procedures=[make_procedure_entry(1, "99.04")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.BilledProcedure[0]")

    def test_billed_procedure_id_format(self, transform_bundle, make_bundle, base_patient):
        """BilledProcedure id combines Claim id and sequence."""
        claim = make_claim(
            claim_id="my-claim",
            procedures=[make_procedure_entry(1, "99.04")],
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.BilledProcedure[0].id", "Claim/my-claim-1")


class TestBilledProcedureCode:
    """Test procedure CHOP code mapping."""

    def test_chop_code_mapped(self, transform_bundle, make_bundle, base_patient):
        """CHOP procedure code is correctly mapped."""
        claim = make_claim(procedures=[make_procedure_entry(1, "99.04")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.BilledProcedure[0].hasCode.termid", "99.04")

    def test_chop_iri_format(self, transform_bundle, make_bundle, base_patient):
        """CHOP IRI uses biomedit.ch/chop format."""
        claim = make_claim(procedures=[make_procedure_entry(1, "99.04")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        iri = get_path(result, "content.BilledProcedure[0].hasCode.iri")
        assert iri == "https://biomedit.ch/rdf/sphn-resource/chop/99.04"


class TestBilledProcedureRank:
    """Test procedure sequence -> rank code mapping."""

    def test_sequence_1_maps_to_principal(self, transform_bundle, make_bundle, base_patient):
        """Procedure sequence 1 maps to Principal (SNOMED 63161005)."""
        claim = make_claim(procedures=[make_procedure_entry(1, "99.04")])
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.BilledProcedure[0].hasRankCode",
            "63161005",
            "/63161005",
        )

    def test_sequence_2_maps_to_supplementary(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Procedure sequence > 1 maps to Supplementary (SNOMED 1354474009)."""
        claim = make_claim(
            procedures=[
                make_procedure_entry(1, "99.04"),
                make_procedure_entry(2, "88.74"),
            ]
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        # Find the second procedure (ID format: Claim/{claim-id}-{sequence})
        procedures = get_path(result, "content.BilledProcedure")
        second_proc = next(p for p in procedures if p.get("id") == "Claim/claim-1-2")

        assert second_proc is not None
        assert second_proc["hasRankCode"]["termid"] == "1354474009"


class TestClaimMetadata:
    """Test Claim metadata mapping."""

    def test_created_mapped_to_diagnosis_record_datetime(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Claim.created maps to BilledDiagnosis.hasRecordDateTime."""
        claim = make_claim(
            diagnoses=[make_diagnosis_entry(1, "I10.9")],
            created="2024-01-25",
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.BilledDiagnosis[0].hasRecordDateTime",
            "2024-01-25",
        )

    def test_created_mapped_to_procedure_start_datetime(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Claim.created maps to BilledProcedure.hasStartDateTime."""
        claim = make_claim(
            procedures=[make_procedure_entry(1, "99.04")],
            created="2024-01-25",
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "content.BilledProcedure[0].hasStartDateTime",
            "2024-01-25",
        )

    def test_encounter_extension_mapped(self, transform_bundle, make_bundle, base_patient):
        """Claim encounter extension maps to hasAdministrativeCase."""
        claim = make_claim(
            diagnoses=[make_diagnosis_entry(1, "I10.9")],
            encounter_ref="Encounter/enc-789",
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        admin_case = get_path(result, "content.BilledDiagnosis[0].hasAdministrativeCase")
        assert admin_case is not None


class TestMultipleDiagnosesAndProcedures:
    """Test claims with multiple diagnoses and procedures."""

    def test_multiple_diagnoses_create_multiple_billed(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Multiple diagnoses create multiple BilledDiagnosis entries."""
        claim = make_claim(
            diagnoses=[
                make_diagnosis_entry(1, "I10.9"),
                make_diagnosis_entry(2, "E11.9"),
                make_diagnosis_entry(3, "J18.9"),
            ]
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        diagnoses = get_path(result, "content.BilledDiagnosis")
        assert diagnoses is not None
        assert len(diagnoses) == 3

    def test_diagnoses_and_procedures_together(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Claim with both diagnoses and procedures creates both types."""
        claim = make_claim(
            diagnoses=[make_diagnosis_entry(1, "I10.9")],
            procedures=[make_procedure_entry(1, "99.04")],
        )
        bundle = make_bundle(base_patient, claim)

        result = transform_bundle(bundle)

        diagnoses = get_path(result, "content.BilledDiagnosis")
        procedures = get_path(result, "content.BilledProcedure")

        assert diagnoses is not None
        assert procedures is not None
        assert len(diagnoses) >= 1
        assert len(procedures) >= 1
