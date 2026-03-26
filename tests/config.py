"""Shared configuration constants for tests and verification scripts."""

from pathlib import Path

# Matchbox server
MATCHBOX_PORT = 8080
MATCHBOX_BASE_URL = f"http://localhost:{MATCHBOX_PORT}/matchboxv3/fhir"

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
MAPS_DIR = PROJECT_ROOT / "maps"
FSH_GENERATED_DIR = PROJECT_ROOT / "fsh-generated" / "resources"

# Main StructureMap URL for transformations
MAIN_STRUCTURE_MAP = (
    "http://research.balgrist.ch/fhir2sphn/StructureMap/BundleToLoopSphn"
)

# Map upload order (dependencies must be uploaded first)
MAP_UPLOAD_ORDER = [
    "Utils.map",
    "EncounterToAdministrativeCase.map",
    "ObservationVitalSignToMeasurement.map",
    "AllergyIntoleranceToAllergy.map",
    "ConditionToProblemCondition.map",
    "ConditionToNursingDiagnosis.map",
    "ClaimToBilledDiagnosisProcedure.map",
    "DiagnosticReportToLabTestEvent.map",
    "MedicationAdministrationToDrugAdministrationEvent.map",
    "ObservationSurveyToAssessmentEvent.map",
    "BundleToLoopSphn.map",
]
