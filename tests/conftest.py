"""
Pytest fixtures for FHIR to SPHN mapping tests.

Provides:
- Matchbox server connection (expects container already running by default)
- Optional container startup via --start-container flag
- Sushi build (regenerates StructureDefinitions from FSH source inside container)
- StructureDefinition upload (POSTs SD JSONs to Matchbox)
- Map upload fixture (uploads .map files from maps/ directory)
- Transform function for executing mappings

Usage:
    # Start container manually first (recommended for development):
    docker compose -f tests/docker-compose.yml up -d
    pytest tests/ -v

    # Or let pytest start the container:
    pytest tests/ -v --start-container
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional

import pytest
import requests

# Configuration
MATCHBOX_PORT = 8080
MATCHBOX_BASE_URL = f"http://localhost:{MATCHBOX_PORT}/matchboxv3/fhir"
# Timeouts
SERVER_STARTUP_TIMEOUT = 300  # 5 minutes
SERVER_POLL_INTERVAL = 5  # seconds

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DOCKER_COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
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


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--start-container",
        action="store_true",
        default=False,
        help="Start the Matchbox container via docker-compose "
        "(default: expect it already running)",
    )
    parser.addoption(
        "--exclude-map",
        action="store",
        default=None,
        help="Exclude a specific map file from upload (e.g., 'AllergyIntoleranceToAllergy.map')",
    )


@pytest.fixture(scope="session")
def matchbox_container(request):
    """
    Manage the Matchbox container lifecycle.

    By default, expects the container to already be running.
    With --start-container: starts the container via docker-compose
    and stops it after tests.
    """
    start_container = request.config.getoption("--start-container")

    if start_container:
        print("Starting Matchbox container via docker-compose...")
        subprocess.run(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "-d"],
            check=True,
            cwd=PROJECT_ROOT,
        )

        yield

        print("Stopping Matchbox container...")
        subprocess.run(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "down"],
            check=True,
            cwd=PROJECT_ROOT,
        )
    else:
        # Container should already be running
        yield


@pytest.fixture(scope="session")
def matchbox_ready(matchbox_container):  # noqa: ARG001 - fixture dependency
    """Wait for Matchbox server to be ready."""
    metadata_url = f"{MATCHBOX_BASE_URL}/metadata"
    start_time = time.time()

    print(f"Waiting for Matchbox server at {metadata_url}...")

    while time.time() - start_time < SERVER_STARTUP_TIMEOUT:
        try:
            response = requests.get(metadata_url, timeout=10)
            if response.status_code == 200:
                print("Matchbox server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(SERVER_POLL_INTERVAL)

    pytest.fail(
        f"Matchbox server did not become ready within {SERVER_STARTUP_TIMEOUT} seconds. "
        "Make sure the container is running: "
        "docker compose -f tests/docker-compose.yml up -d"
    )


def run_sushi_build() -> None:
    """Run sushi build inside the Matchbox container to regenerate StructureDefinitions."""
    result = subprocess.run(
        [
            "docker", "compose", "-f", str(DOCKER_COMPOSE_FILE),
            "exec", "matchbox",
            "sh", "-c", "cd /home/matchbox/maps && sushi build",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sushi build failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout[-1000:]}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
    print("  sushi build completed successfully")


def upload_structure_definitions() -> None:
    """Upload StructureDefinition JSON files from fsh-generated/resources/ to Matchbox."""
    sd_files = sorted(FSH_GENERATED_DIR.glob("StructureDefinition-*.json"))
    if not sd_files:
        print("  No StructureDefinition files found, skipping")
        return

    uploaded = 0
    for sd_path in sd_files:
        sd_json = json.loads(sd_path.read_text())
        resp = requests.post(
            f"{MATCHBOX_BASE_URL}/StructureDefinition",
            json=sd_json,
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to upload {sd_path.name}: {resp.status_code} - "
                f"{resp.text[:500]}"
            )
        uploaded += 1

    print(f"  Uploaded {uploaded} StructureDefinitions")


def upload_map(map_path: Path) -> None:
    """Upload a single StructureMap to Matchbox."""
    map_content = map_path.read_text()
    response = requests.post(
        f"{MATCHBOX_BASE_URL}/StructureMap",
        data=map_content,
        headers={"Content-Type": "text/fhir-mapping"},
        timeout=60,
    )
    if response.status_code not in (200, 201):
        raise AssertionError(
            f"Failed to upload {map_path.name}: {response.status_code} - "
            f"{response.text[:500]}"
        )


def delete_map(map_url: str) -> bool:
    """Delete a StructureMap from Matchbox by URL. Returns True if deleted."""
    # First, find the map's ID by searching
    search_response = requests.get(
        f"{MATCHBOX_BASE_URL}/StructureMap",
        params={"url": map_url},
        headers={"Accept": "application/fhir+json"},
        timeout=30,
    )
    if search_response.status_code != 200:
        return False

    bundle = search_response.json()
    if not bundle.get("entry"):
        return False

    # Delete each matching resource
    for entry in bundle["entry"]:
        resource_id = entry["resource"]["id"]
        delete_response = requests.delete(
            f"{MATCHBOX_BASE_URL}/StructureMap/{resource_id}",
            timeout=30,
        )
        if delete_response.status_code not in (200, 204):
            return False

    return True


def delete_all_maps() -> None:
    """Delete all StructureMaps from Matchbox to ensure clean slate."""
    base_url = "http://research.balgrist.ch/fhir2sphn/StructureMap/"

    # Delete in reverse order (dependents first)
    for map_name in reversed(MAP_UPLOAD_ORDER):
        map_url = base_url + map_name.replace(".map", "")
        delete_map(map_url)


@pytest.fixture(scope="session")
def maps_uploaded(matchbox_ready, request) -> List[str]:  # noqa: ARG001 - fixture dependency
    """
    Build and upload StructureDefinitions and StructureMaps to Matchbox.

    Steps:
    1. Run sushi build (inside container) to regenerate SDs from FSH source
    2. Upload StructureDefinitions via REST API
    3. Upload StructureMaps from maps/ directory

    Use --exclude-map to skip a specific map for coverage testing.

    Returns list of uploaded map names.
    """
    exclude_map = request.config.getoption("--exclude-map")
    uploaded = []

    # Build and upload StructureDefinitions
    print("Running sushi build inside container...")
    run_sushi_build()

    print("Uploading StructureDefinitions...")
    upload_structure_definitions()

    print(f"Uploading StructureMaps from {MAPS_DIR}...")

    for map_name in MAP_UPLOAD_ORDER:
        if exclude_map and map_name == exclude_map:
            print(f"  SKIPPING {map_name} (excluded via --exclude-map)")
            continue

        map_path = MAPS_DIR / map_name
        if map_path.exists():
            print(f"  Uploading {map_name}...")
            upload_map(map_path)
            uploaded.append(map_name)
        else:
            print(f"  Warning: {map_name} not found")

    print(f"Uploaded {len(uploaded)} StructureMaps")
    return uploaded


@pytest.fixture(scope="session")
def transform_bundle(maps_uploaded) -> Callable:  # noqa: ARG001 - fixture dependency
    """
    Fixture that returns a function to transform FHIR Bundles.

    Depends on maps_uploaded to ensure all StructureMaps are available.

    Usage:
        result = transform_bundle(bundle_dict)
        result = transform_bundle(bundle_dict, source_map="http://custom/StructureMap/Name")
    """

    def _transform(
        bundle: dict,
        source_map: Optional[str] = None,
    ) -> dict:
        """
        Transform a FHIR Bundle using Matchbox.

        Args:
            bundle: The FHIR Bundle as a dict
            source_map: Optional StructureMap URL (defaults to BundleToLoopSphn)

        Returns:
            The transformed result as a dict
        """
        if source_map is None:
            source_map = MAIN_STRUCTURE_MAP

        transform_url = f"{MATCHBOX_BASE_URL}/StructureMap/$transform"
        params = {"source": source_map}
        headers = {
            "Content-Type": "application/fhir+json;fhirVersion=4.0",
            "Accept": "application/fhir+json;fhirVersion=4.0",
        }

        response = requests.post(
            transform_url,
            params=params,
            json=bundle,
            headers=headers,
            timeout=120,
        )

        if response.status_code != 200:
            raise AssertionError(
                f"Transform failed with status {response.status_code}: "
                f"{response.text[:1000]}"
            )

        return response.json()

    return _transform


# Helper fixtures for creating test bundles


@pytest.fixture
def make_bundle():
    """Factory fixture for creating FHIR Bundles with resources."""

    def _make_bundle(*resources, bundle_id="test-bundle"):
        """
        Create a FHIR Bundle containing the given resources.

        Args:
            *resources: FHIR resources to include
            bundle_id: Optional bundle ID

        Returns:
            A FHIR Bundle dict
        """
        entries = [{"resource": r} for r in resources]

        return {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "collection",
            "meta": {"lastUpdated": "2024-01-15T10:30:00Z"},
            "entry": entries,
        }

    return _make_bundle


@pytest.fixture
def base_patient():
    """A minimal Patient resource for testing."""
    return {
        "resourceType": "Patient",
        "id": "test-patient-1",
        "meta": {"source": "http://example.org/ehr"},
        "identifier": [{"system": "http://example.org/patients", "value": "12345"}],
    }
