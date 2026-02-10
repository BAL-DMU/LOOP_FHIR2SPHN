"""
Tests for BundleToLoopSphn.map

Tests the main orchestrating map that handles:
- Patient demographics (gender, birthDate, deceased)
- Consent
- DataRelease, DataProvider, SourceSystem, SubjectPseudoIdentifier
"""

from tests.helpers import (
    assert_code_mapped,
    assert_list_length,
    assert_path_equals,
    assert_path_exists,
    get_path,
)


def make_consent(policy_code="OPTIN", datetime="2024-01-10T08:00:00Z"):
    """Create a Consent resource."""
    return {
        "resourceType": "Consent",
        "id": "consent-1",
        "meta": {"source": "http://example.org/ehr"},
        "status": "active",
        "scope": {
            "coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "research"}
            ]
        },
        "category": [
            {"coding": [{"system": "http://snomed.info/sct", "code": "59284002"}]}
        ],
        "dateTime": datetime,
        "policyRule": {
            "coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": policy_code}
            ]
        },
    }


def make_patient_with_org(org_id="org-1", identifier="HOSP123", name="Test Hospital"):
    """Create a Patient with a contained Organization."""
    return {
        "resourceType": "Patient",
        "id": "pat-1",
        "meta": {"source": "http://example.org/ehr"},
        "contained": [
            {
                "resourceType": "Organization",
                "id": org_id,
                "identifier": [{"value": identifier}],
                "name": name,
            }
        ],
        "managingOrganization": {"reference": f"#{org_id}"},
    }


class TestPatientGender:
    """Test gender -> AdministrativeSex mapping."""

    def test_male_maps_to_snomed_248153007(self, transform_bundle, make_bundle, base_patient):
        """Male gender maps to SNOMED CT 248153007."""
        base_patient["gender"] = "male"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeSex[0].hasCode",
            "248153007",
            "/248153007",
        )

    def test_female_maps_to_snomed_248152002(self, transform_bundle, make_bundle, base_patient):
        """Female gender maps to SNOMED CT 248152002."""
        base_patient["gender"] = "female"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeSex[0].hasCode",
            "248152002",
            "/248152002",
        )

    def test_other_maps_to_snomed_32570681000036106(
        self, transform_bundle, make_bundle, base_patient
    ):
        """Other gender maps to SNOMED CT 32570681000036106."""
        base_patient["gender"] = "other"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_code_mapped(
            result,
            "content.AdministrativeSex[0].hasCode",
            "32570681000036106",
            "/32570681000036106",
        )

    def test_no_gender_no_administrative_sex(self, transform_bundle, make_bundle, base_patient):
        """Patient without gender produces no AdministrativeSex."""
        # Ensure no gender field
        base_patient.pop("gender", None)
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        admin_sex = get_path(result, "content.AdministrativeSex")
        assert admin_sex is None or len(admin_sex) == 0


class TestPatientBirthDate:
    """Test birthDate -> Birth mapping."""

    def test_birthdate_creates_birth(self, transform_bundle, make_bundle, base_patient):
        """BirthDate creates Birth with parsed date components."""
        base_patient["birthDate"] = "1990-05-15"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Birth[0]")
        assert_path_exists(result, "content.Birth[0].hasDate")

    def test_birthdate_year_extracted(self, transform_bundle, make_bundle, base_patient):
        """Birth year is correctly extracted."""
        base_patient["birthDate"] = "1990-05-15"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.Birth[0].hasDate.hasYear", "1990")

    def test_birthdate_month_extracted(self, transform_bundle, make_bundle, base_patient):
        """Birth month is correctly extracted with -- prefix."""
        base_patient["birthDate"] = "1990-05-15"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.Birth[0].hasDate.hasMonth", "--05")

    def test_birthdate_day_extracted(self, transform_bundle, make_bundle, base_patient):
        """Birth day is correctly extracted with --- prefix."""
        base_patient["birthDate"] = "1990-05-15"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.Birth[0].hasDate.hasDay", "---15")

    def test_no_birthdate_no_birth(self, transform_bundle, make_bundle, base_patient):
        """Patient without birthDate produces no Birth."""
        base_patient.pop("birthDate", None)
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        birth = get_path(result, "content.Birth")
        assert birth is None or len(birth) == 0


class TestPatientDeceased:
    """Test deceased -> Death mapping."""

    def test_deceased_boolean_true_creates_death(
        self, transform_bundle, make_bundle, base_patient
    ):
        """deceasedBoolean=true creates Death without date."""
        base_patient["deceasedBoolean"] = True
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Death[0]")
        assert_path_exists(result, "content.Death[0].id")

    def test_deceased_boolean_false_no_death(self, transform_bundle, make_bundle, base_patient):
        """deceasedBoolean=false does not create Death."""
        base_patient["deceasedBoolean"] = False
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        death = get_path(result, "content.Death")
        assert death is None or len(death) == 0

    def test_deceased_datetime_creates_death_with_date(
        self, transform_bundle, make_bundle, base_patient
    ):
        """deceasedDateTime creates Death with date components."""
        base_patient["deceasedDateTime"] = "2023-12-01"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Death[0]")
        assert_path_exists(result, "content.Death[0].hasDate")
        assert_path_equals(result, "content.Death[0].hasDate.hasYear", "2023")
        assert_path_equals(result, "content.Death[0].hasDate.hasMonth", "--12")
        assert_path_equals(result, "content.Death[0].hasDate.hasDay", "---01")


class TestConsent:
    """Test Consent resource mapping."""

    def test_consent_optin_maps_to_snomed_385645004(self, transform_bundle, make_bundle):
        """Consent with OPTIN policy maps to SNOMED 385645004."""
        patient = {"resourceType": "Patient", "id": "pat-1", "meta": {"source": "http://example.org/ehr"}}
        bundle = make_bundle(patient, make_consent(policy_code="OPTIN"))

        result = transform_bundle(bundle)

        assert_path_exists(result, "content.Consent[0]")
        assert_code_mapped(result, "content.Consent[0].hasStatusCode", "385645004")

    def test_consent_optout_maps_to_snomed_443390004(self, transform_bundle, make_bundle):
        """Consent with OPTOUT policy maps to SNOMED 443390004."""
        patient = {"resourceType": "Patient", "id": "pat-1", "meta": {"source": "http://example.org/ehr"}}
        bundle = make_bundle(patient, make_consent(policy_code="OPTOUT"))

        result = transform_bundle(bundle)

        assert_code_mapped(result, "content.Consent[0].hasStatusCode", "443390004")

    def test_consent_datetime_mapped(self, transform_bundle, make_bundle):
        """Consent dateTime is mapped to hasDateTime."""
        patient = {"resourceType": "Patient", "id": "pat-1", "meta": {"source": "http://example.org/ehr"}}
        bundle = make_bundle(patient, make_consent())

        result = transform_bundle(bundle)

        assert_path_equals(result, "content.Consent[0].hasDateTime", "2024-01-10T08:00:00Z")

    def test_consent_category_snomed_mapped(self, transform_bundle, make_bundle):
        """Consent category SNOMED code is mapped to hasTypeCode."""
        patient = {"resourceType": "Patient", "id": "pat-1", "meta": {"source": "http://example.org/ehr"}}
        bundle = make_bundle(patient, make_consent())

        result = transform_bundle(bundle)

        assert_code_mapped(result, "content.Consent[0].hasTypeCode", "59284002")


class TestDataRelease:
    """Test DataRelease creation from Bundle."""

    def test_data_release_created(self, transform_bundle, make_bundle, base_patient):
        """Bundle creates DataRelease with extraction datetime."""
        bundle = make_bundle(base_patient)
        bundle["meta"]["lastUpdated"] = "2024-01-15T10:30:00Z"

        result = transform_bundle(bundle)

        assert_path_exists(result, "DataRelease")
        assert_path_equals(result, "DataRelease.hasExtractionDateTime", "2024-01-15T10:30:00Z")

    def test_data_release_id_from_bundle(self, transform_bundle, make_bundle, base_patient):
        """DataRelease id comes from bundle id."""
        bundle = make_bundle(base_patient, bundle_id="my-bundle-123")

        result = transform_bundle(bundle)

        assert_path_equals(result, "DataRelease.id", "my-bundle-123")


class TestSourceSystem:
    """Test SourceSystem creation from meta.source."""

    def test_source_system_created(self, transform_bundle, make_bundle, base_patient):
        """Resource meta.source creates SourceSystem."""
        base_patient["meta"]["source"] = "http://example.org/ehr"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        source_systems = get_path(result, "content.SourceSystem")
        assert source_systems is not None
        assert len(source_systems) >= 1
        assert any(ss.get("id") == "http://example.org/ehr" for ss in source_systems)

    def test_source_system_strips_fragment(self, transform_bundle, make_bundle, base_patient):
        """SourceSystem id strips URL fragment."""
        base_patient["meta"]["source"] = "http://example.org/ehr#patient-123"
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        source_systems = get_path(result, "content.SourceSystem")
        assert source_systems is not None
        # Fragment should be stripped
        assert any(ss.get("id") == "http://example.org/ehr" for ss in source_systems)


class TestSubjectPseudoIdentifier:
    """Test SubjectPseudoIdentifier creation from Patient."""

    def test_subject_pseudo_identifier_created(self, transform_bundle, make_bundle, base_patient):
        """Patient creates SubjectPseudoIdentifier."""
        base_patient["id"] = "patient-abc"
        base_patient["identifier"] = [
            {"system": "http://example.org/patients", "value": "12345"}
        ]
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_exists(result, "SubjectPseudoIdentifier")
        assert_path_equals(result, "SubjectPseudoIdentifier.id", "Patient/patient-abc")

    def test_subject_identifier_combined(self, transform_bundle, make_bundle, base_patient):
        """SubjectPseudoIdentifier hasIdentifier combines system and value."""
        base_patient["identifier"] = [
            {"system": "http://example.org/patients", "value": "12345"}
        ]
        bundle = make_bundle(base_patient)

        result = transform_bundle(bundle)

        assert_path_equals(
            result,
            "SubjectPseudoIdentifier.hasIdentifier",
            "http://example.org/patients|12345",
        )


class TestDataProvider:
    """Test DataProvider creation from Patient.managingOrganization (contained)."""

    def test_data_provider_from_contained_organization(self, transform_bundle, make_bundle):
        """Contained Organization creates DataProvider."""
        bundle = make_bundle(make_patient_with_org())

        result = transform_bundle(bundle)

        assert_path_exists(result, "DataProvider")
        assert_path_equals(result, "DataProvider.id", "org-1")

    def test_data_provider_institution_code(self, transform_bundle, make_bundle):
        """DataProvider hasInstitutionCode from Organization."""
        bundle = make_bundle(make_patient_with_org())

        result = transform_bundle(bundle)

        assert_path_exists(result, "DataProvider.hasInstitutionCode")
        assert_path_equals(result, "DataProvider.hasInstitutionCode.hasIdentifier", "HOSP123")
        assert_path_equals(result, "DataProvider.hasInstitutionCode.hasName", "Test Hospital")
