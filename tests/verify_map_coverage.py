#!/usr/bin/env python3
"""
Map Coverage Verification via Mutation Testing

Verifies that each mapping rule in FML map files has test coverage by:
1. Parsing each .map file to extract removable mapping rules
2. Commenting out each rule one by one
3. Re-uploading the modified map to Matchbox
4. Running relevant tests to see if at least one fails
5. Restoring original map
6. Generating a coverage report

Usage:
    # Run coverage verification for all maps
    python tests/verify_map_coverage.py

    # Run for specific map
    python tests/verify_map_coverage.py --map AllergyIntoleranceToAllergy.map

    # Generate report only (dry run - no test execution)
    python tests/verify_map_coverage.py --dry-run

    # Verbose output
    python tests/verify_map_coverage.py -v
"""

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

# Configuration
MATCHBOX_BASE_URL = "http://localhost:8080/matchboxv3/fhir"
PROJECT_ROOT = Path(__file__).parent.parent
MAPS_DIR = PROJECT_ROOT / "maps"
TESTS_DIR = PROJECT_ROOT / "tests" / "maps"

# Map upload order (dependencies first)
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

# Map file -> Test file mapping
MAP_TO_TEST = {
    "AllergyIntoleranceToAllergy.map": "test_allergy_intolerance.py",
    "BundleToLoopSphn.map": "test_bundle_to_loop_sphn.py",
    "ClaimToBilledDiagnosisProcedure.map": "test_claim_billed.py",
    "ConditionToNursingDiagnosis.map": "test_condition_nursing.py",
    "ConditionToProblemCondition.map": "test_condition_problem.py",
    "DiagnosticReportToLabTestEvent.map": "test_diagnostic_report.py",
    "EncounterToAdministrativeCase.map": "test_encounter_to_admin_case.py",
    "MedicationAdministrationToDrugAdministrationEvent.map": "test_medication_admin.py",
    "ObservationSurveyToAssessmentEvent.map": "test_observation_survey.py",
    "ObservationVitalSignToMeasurement.map": "test_vital_sign_to_measurement.py",
    "Utils.map": "test_utils.py",
}


@dataclass
class MapRule:
    """Represents a removable mapping rule in an FML file."""

    map_file: str
    line_number: int
    line_content: str
    rule_type: str  # 'field_mapping', 'id_generation', 'helper_call', 'translate', etc.
    description: str
    # Multi-line rules span multiple lines
    end_line: Optional[int] = None

    @property
    def lines(self) -> str:
        if self.end_line:
            return f"{self.line_number}-{self.end_line}"
        return str(self.line_number)


@dataclass
class RuleTestResult:
    """Result of testing a single rule mutation."""

    rule: MapRule
    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    is_covered: bool = False
    failed_tests: list = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class MapCoverageReport:
    """Coverage report for a single map file."""

    map_file: str
    total_rules: int = 0
    covered_rules: int = 0
    missing_rules: list = field(default_factory=list)
    rule_results: list = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.total_rules == 0:
            return 100.0
        return (self.covered_rules / self.total_rules) * 100


class FMLParser:
    """Parser for FHIR Mapping Language files to extract removable rules.

    Extracts individual mapping statements that can be commented out for
    mutation testing. Strategy: find all semicolon-terminated statements
    at ANY nesting level, not just top-level.

    Rule types:
    - Field mappings: source.x as y -> target.z = value;
    - ID generations: target.id = ('prefix' & %id);
    - Helper calls: source.x as y then helper(y, z);
    - Block creates: source -> target.field = create('Type') as x then { ... };
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def parse_map_file(self, map_path: Path) -> list[MapRule]:
        """Extract removable rules from an FML map file."""
        content = map_path.read_text()
        map_name = map_path.name
        rules = []

        lines = content.split("\n")

        # Find all statements, including nested ones
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip non-statement lines
            if self._is_skip_line(stripped):
                i += 1
                continue

            # Check if this line is or contains a statement
            rule = self._try_parse_statement(lines, i, map_name)
            if rule and self._is_testable_rule(rule):
                rules.append(rule)

            i += 1

        return rules

    def _is_skip_line(self, stripped: str) -> bool:
        """Check if line should be skipped."""
        if not stripped:
            return True
        if stripped.startswith("//"):
            return True

        # Structural-only lines
        skip_patterns = [
            r"^map\s+",
            r"^uses\s+",
            r"^imports\s+",
            r"^group\s+\w+\(",
            r"^\}\s*(\"[^\"]+\")?\s*;?\s*(//.*)?$",
            r"^conceptmap\s+",
            r"^prefix\s+",
            r"^s:\S+\s*==",
        ]
        return any(re.match(p, stripped) for p in skip_patterns)

    def _try_parse_statement(
        self, lines: list[str], idx: int, map_name: str
    ) -> Optional[MapRule]:
        """Try to parse a statement starting at line idx."""
        line = lines[idx]
        stripped = line.strip()
        line_num = idx + 1

        # Detect statement start patterns
        # Pattern 1: identifier[.prop] as var -> ... or then ...
        # Pattern 2: identifier[.prop] first as var where ... -> ...
        # Pattern 3: identifier -> target.prop = ...
        if not re.match(r"^\w+(\.[\w.]+)?(\s+first)?\s+(as\s+\w+\s*)?(->|then|where)", stripped):
            return None

        # Collect the complete statement
        # Simple case: ends on same line with ;, no nested block
        if ";" in line and "{" not in line.split(";")[0]:
            # Statement ends on this line
            return self._create_rule(stripped, line_num, None, map_name)

        # Check if this starts a block (has 'then {')
        if " then {" in line or "then{" in line:
            # This is a block - collect until matching }
            end_idx = self._find_block_end(lines, idx)
            block_content = "\n".join(lines[idx : end_idx + 1])
            return self._create_rule(
                block_content.strip(), line_num, end_idx + 1, map_name
            )

        # Multi-line statement without block - collect until ;
        end_idx = self._find_semicolon(lines, idx)
        content = "\n".join(lines[idx : end_idx + 1])
        return self._create_rule(
            content.strip(),
            line_num,
            end_idx + 1 if end_idx > idx else None,
            map_name,
        )

    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        """Find the line where a block ends (matching })."""
        brace_depth = 0
        for i in range(start_idx, len(lines)):
            line = lines[i]
            brace_depth += line.count("{") - line.count("}")
            if brace_depth == 0 and i > start_idx:
                return i
        return start_idx

    def _find_semicolon(self, lines: list[str], start_idx: int) -> int:
        """Find the line where statement ends with ;."""
        paren_depth = 0
        for i in range(start_idx, min(len(lines), start_idx + 20)):
            line = lines[i]
            for char in line:
                if char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth -= 1
            if ";" in line and paren_depth == 0:
                return i
        return start_idx

    def _create_rule(
        self, content: str, start_line: int, end_line: Optional[int], map_name: str
    ) -> MapRule:
        """Create a MapRule."""
        rule_type, description = self._classify_rule(content)
        return MapRule(
            map_file=map_name,
            line_number=start_line,
            line_content=content,
            rule_type=rule_type,
            description=description,
            end_line=end_line if end_line and end_line != start_line else None,
        )

    def _classify_rule(self, content: str) -> tuple[str, str]:
        """Classify rule type and generate description."""
        # ID assignment
        if re.search(r"\.id\s*=\s*(\(|uuid)", content):
            match = re.search(r"\.id\s*=\s*\(['\"]([^'\"&]+)", content)
            if match:
                return "id_generation", f"ID: '{match.group(1).strip()}' prefix"
            if "uuid()" in content:
                return "id_generation", "ID: uuid()"
            return "id_generation", "ID assignment"

        # Concept map translation
        if "translate(" in content:
            match = re.search(r"translate\([^,]+,\s*['\"]#([^'\"]+)['\"]\)", content)
            if match:
                return "translate", f"translate(#{match.group(1)})"
            return "translate", "translate()"

        # Helper call (without block)
        if " then " in content and " then {" not in content:
            match = re.search(r"then\s+(\w+)\(", content)
            if match:
                return "helper_call", f"{match.group(1)}()"
            return "helper_call", "helper call"

        # Block with create
        if " then {" in content:
            match = re.search(r"(\w+\.\w+)\s*=\s*create\(['\"](\w+)['\"]\)", content)
            if match:
                return "block_create", f"Create {match.group(2)} -> {match.group(1)}"
            return "block_mapping", "block mapping"

        # Field mapping
        if "->" in content and "=" in content:
            match = re.search(
                r"(\w+\.[\w.]+)\s+as\s+\w+\s*->\s*(\w+\.[\w.]+)\s*=",
                content,
            )
            if match:
                return "field_mapping", f"{match.group(1)} -> {match.group(2)}"

            match = re.search(r"->\s*(\w+\.[\w.]+)\s*=", content)
            if match:
                return "field_mapping", f"-> {match.group(1)}"

        # Fallback
        single_line = " ".join(content.split())[:55]
        return "unknown", single_line + ("..." if len(content) > 55 else "")

    def _is_testable_rule(self, rule: MapRule) -> bool:
        """Check if rule is worth testing."""
        if rule.rule_type in (
            "field_mapping",
            "id_generation",
            "translate",
            "helper_call",
            "block_create",
        ):
            return True

        if rule.rule_type == "block_mapping":
            return "create(" in rule.line_content

        return True


class MatchboxClient:
    """Client for interacting with Matchbox server."""

    def __init__(self, base_url: str = MATCHBOX_BASE_URL, verbose: bool = False):
        self.base_url = base_url
        self.verbose = verbose

    def is_ready(self) -> bool:
        """Check if Matchbox server is ready."""
        try:
            response = requests.get(f"{self.base_url}/metadata", timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def upload_map(self, map_content: str) -> bool:
        """Upload a StructureMap to Matchbox."""
        try:
            response = requests.post(
                f"{self.base_url}/StructureMap",
                data=map_content,
                headers={"Content-Type": "text/fhir-mapping"},
                timeout=60,
            )
            if self.verbose:
                print(f"  Upload response: {response.status_code}")
            return response.status_code in (200, 201)
        except requests.exceptions.RequestException as e:
            if self.verbose:
                print(f"  Upload error: {e}")
            return False

    def delete_map(self, map_url: str) -> bool:
        """Delete a StructureMap from Matchbox by URL."""
        try:
            # Search for the map
            search_response = requests.get(
                f"{self.base_url}/StructureMap",
                params={"url": map_url},
                headers={"Accept": "application/fhir+json"},
                timeout=30,
            )
            if search_response.status_code != 200:
                return False

            bundle = search_response.json()
            if not bundle.get("entry"):
                return True  # Already deleted

            # Delete each matching resource
            for entry in bundle["entry"]:
                resource_id = entry["resource"]["id"]
                delete_response = requests.delete(
                    f"{self.base_url}/StructureMap/{resource_id}",
                    timeout=30,
                )
                if delete_response.status_code not in (200, 204):
                    return False

            return True
        except requests.exceptions.RequestException:
            return False

    def get_map_url(self, map_name: str) -> str:
        """Get the canonical URL for a map file."""
        base = "http://research.balgrist.ch/fhir2sphn/StructureMap/"
        return base + map_name.replace(".map", "")


class MutationTester:
    """Performs mutation testing on FML map files."""

    def __init__(
        self,
        matchbox: MatchboxClient,
        parser: FMLParser,
        verbose: bool = False,
        dry_run: bool = False,
    ):
        self.matchbox = matchbox
        self.parser = parser
        self.verbose = verbose
        self.dry_run = dry_run

    def test_map_coverage(self, map_name: str) -> MapCoverageReport:
        """Test coverage for a single map file."""
        report = MapCoverageReport(map_file=map_name)

        map_path = MAPS_DIR / map_name
        if not map_path.exists():
            report.error_message = f"Map file not found: {map_path}"
            return report

        # Parse rules
        rules = self.parser.parse_map_file(map_path)
        report.total_rules = len(rules)

        if self.verbose:
            print(f"\n=== {map_name} ({len(rules)} rules) ===")

        # Get test file
        test_file = MAP_TO_TEST.get(map_name)
        if not test_file:
            print(f"  WARNING: No test file mapped for {map_name}")
            return report

        test_path = TESTS_DIR / test_file
        if not test_path.exists():
            print(f"  WARNING: Test file not found: {test_path}")
            return report

        # Store original content
        original_content = map_path.read_text()

        # Test each rule
        for rule in rules:
            result = self._test_rule_mutation(
                map_name, map_path, original_content, rule, test_path
            )
            report.rule_results.append(result)

            if result.is_covered:
                report.covered_rules += 1
            else:
                report.missing_rules.append(rule)

        return report

    def _test_rule_mutation(
        self,
        map_name: str,
        map_path: Path,
        original_content: str,
        rule: MapRule,
        test_path: Path,
    ) -> RuleTestResult:
        """Test a single rule mutation.

        Strategy: modify the actual .map file on disk, then run pytest which
        will upload the modified version via maps_uploaded fixture. After the
        test, restore the original file.
        """
        result = RuleTestResult(rule=rule)

        if self.verbose:
            print(f"  Testing rule line {rule.lines}: {rule.description}")

        if self.dry_run:
            result.is_covered = True  # Assume covered in dry run
            return result

        # Create mutated content (comment out the rule)
        mutated_content = self._comment_out_rule(original_content, rule)

        try:
            # Write mutated content to the actual map file
            map_path.write_text(mutated_content)

            # Run tests (pytest will upload the modified map file)
            passed, failed, errors, failed_tests = self._run_tests(test_path)
            result.tests_passed = passed
            result.tests_failed = failed
            result.tests_error = errors
            result.failed_tests = failed_tests

            # Rule is covered if at least one test fails or errors
            result.is_covered = failed > 0 or errors > 0

            if self.verbose:
                status = "COVERED" if result.is_covered else "MISSING"
                print(f"    [{status}] passed={passed}, failed={failed}, errors={errors}")

        finally:
            # Always restore the original map file
            map_path.write_text(original_content)

        return result

    def _comment_out_rule(self, content: str, rule: MapRule) -> str:
        """Comment out a rule in the map content."""
        lines = content.split("\n")
        start = rule.line_number - 1  # Convert to 0-indexed
        end = (rule.end_line - 1) if rule.end_line else start

        for i in range(start, end + 1):
            if i < len(lines) and not lines[i].strip().startswith("//"):
                lines[i] = "// MUTATION: " + lines[i]

        return "\n".join(lines)

    def _run_tests(self, test_path: Path) -> tuple[int, int, int, list[str]]:
        """Run pytest and return (passed, failed, errors, failed_test_names)."""
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(test_path),
                    "-v",
                    "--tb=line",
                    "-q",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=PROJECT_ROOT,
            )

            output = result.stdout + result.stderr

            if self.verbose and result.returncode != 0:
                # Show last few lines on failure for debugging
                out_lines = output.strip().split("\n")
                print("    pytest output (last 5 lines):")
                for line in out_lines[-5:]:
                    print(f"      {line}")

            # Parse test results from summary line
            # pytest outputs: "X passed", "X failed", "X error" in various orders
            passed = failed = errors = 0
            failed_tests = []

            # Extract individual counts
            passed_match = re.search(r"(\d+) passed", output)
            if passed_match:
                passed = int(passed_match.group(1))

            failed_match = re.search(r"(\d+) failed", output)
            if failed_match:
                failed = int(failed_match.group(1))

            error_match = re.search(r"(\d+) error", output)
            if error_match:
                errors = int(error_match.group(1))

            # Extract failed test names
            for line in output.split("\n"):
                if "FAILED" in line:
                    # Pattern: FAILED tests/maps/test_file.py::Class::method
                    match = re.search(r"FAILED\s+(\S+)", line)
                    if match:
                        failed_tests.append(match.group(1))

            return passed, failed, errors, failed_tests

        except subprocess.TimeoutExpired:
            return 0, 0, 1, ["timeout"]
        except Exception as e:
            return 0, 0, 1, [str(e)]


def print_report(reports: list[MapCoverageReport]) -> None:
    """Print the coverage report."""
    print("\n" + "=" * 60)
    print("MAP COVERAGE VERIFICATION REPORT")
    print("=" * 60)

    total_rules = 0
    total_covered = 0

    for report in reports:
        total_rules += report.total_rules
        total_covered += report.covered_rules

        print(f"\n{report.map_file} ({report.total_rules} rules)")
        print("-" * 40)

        for result in report.rule_results:
            status = "[COVERED]" if result.is_covered else "[MISSING]"
            print(f"  {status} line {result.rule.lines}: {result.rule.description}")

            if not result.is_covered and result.failed_tests:
                print(f"           Failed tests: {', '.join(result.failed_tests)}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    coverage_pct = (total_covered / total_rules * 100) if total_rules > 0 else 100
    print(f"Total rules: {total_rules}")
    print(f"Covered: {total_covered} ({coverage_pct:.1f}%)")
    print(f"Missing: {total_rules - total_covered} rules need tests")

    # List missing rules
    missing = []
    for report in reports:
        for rule in report.missing_rules:
            missing.append((report.map_file, rule))

    if missing:
        print("\n" + "=" * 60)
        print("TESTS TO ADD")
        print("=" * 60)
        for i, (map_file, rule) in enumerate(missing, 1):
            test_file = MAP_TO_TEST.get(map_file, "unknown")
            print(f"{i}. {test_file}: test {rule.description}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify map coverage via mutation testing"
    )
    parser.add_argument(
        "--map",
        help="Test only a specific map file (e.g., AllergyIntoleranceToAllergy.map)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse rules only, don't run tests",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    # Initialize components
    fml_parser = FMLParser(verbose=args.verbose)
    matchbox = MatchboxClient(verbose=args.verbose)
    tester = MutationTester(
        matchbox, fml_parser, verbose=args.verbose, dry_run=args.dry_run
    )

    # Check Matchbox connectivity (unless dry run)
    if not args.dry_run:
        print("Checking Matchbox server connectivity...")
        if not matchbox.is_ready():
            print("ERROR: Matchbox server is not available at", MATCHBOX_BASE_URL)
            print("Start it with: docker compose -f tests/docker-compose.yml up -d")
            sys.exit(1)
        print("Matchbox server is ready.")

    # Determine which maps to test
    if args.map:
        maps_to_test = [args.map]
    else:
        maps_to_test = MAP_UPLOAD_ORDER

    # Run coverage tests
    reports = []
    for map_name in maps_to_test:
        if map_name not in MAP_TO_TEST:
            if args.verbose:
                print(f"Skipping {map_name} (no test file mapped)")
            continue

        report = tester.test_map_coverage(map_name)
        reports.append(report)

    # Print report
    print_report(reports)


if __name__ == "__main__":
    main()
