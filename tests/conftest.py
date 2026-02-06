"""
Pytest fixtures for FHIR to SPHN mapping tests.

Provides:
- Matchbox server connection (expects container already running by default)
- Optional container startup via --start-container flag
- Transform function for executing mappings

The pre-built Docker image already includes all StructureDefinitions and StructureMaps,
so no upload step is needed.

Usage:
    # Start container manually first (recommended for development):
    docker compose -f tests/docker-compose.yml up -d
    pytest tests/ -v

    # Or let pytest start the container:
    pytest tests/ -v --start-container
"""

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

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

# Main StructureMap URL for transformations
MAIN_STRUCTURE_MAP = (
    "http://research.balgrist.ch/fhir2sphn/StructureMap/BundleToLoopSphn"
)


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--start-container",
        action="store_true",
        default=False,
        help="Start the Matchbox container via docker-compose "
        "(default: expect it already running)",
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


@pytest.fixture(scope="session")
def transform_bundle(matchbox_ready) -> Callable:  # noqa: ARG001 - fixture dependency
    """
    Fixture that returns a function to transform FHIR Bundles.

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
