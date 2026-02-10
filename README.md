# LOOP BMIP FHIR to SPHN Mapping

FHIR to SPHN mappings for LOOP BMIP using [FHIR Mapping Language (FML)](https://build.fhir.org/mapping-language.html)
* Mappings: [maps](maps/)

StructureDefinitions for the target LOOP schema is defined using [FHIR Shorthand (FSH)](https://build.fhir.org/ig/HL7/fhir-shorthand/)
* FSH: [input/fsh/LogicalModel.fsh](input/fsh/LogicalModel.fsh)

# Install
* Install SUSHI from https://github.com/FHIR/sushi
* For building the IG, jekyll is required:
    * `sudo apt install jekyll`
* Optional VS Code extensions for development:
    * [FHIR Shorthand](https://marketplace.visualstudio.com/items?itemName=MITRE-Health.vscode-language-fsh)
    * [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)

An FML engine is required like [HAPI-FHIR Validator Cli](https://confluence.hl7.org/pages/viewpage.action?pageId=76158820#UsingtheFHIRMappingLanguage-runtransformsjavavalidatorRunTransformsviatheJavaValidatorJar) or [Matchbox](https://ahdis.github.io/matchbox/) (recommended)

**Recommended versions:** Use at least 6.5.0 for HAPI-FHIR Validator Cli and 4.0.1 for Matchbox or later. These releases contain critical performance improvements required to transform large amount of data (see https://github.com/hapifhir/org.hl7.fhir.core/pull/1704 / https://github.com/ahdis/matchbox/pull/362) and corresponding issues [#1703](https://github.com/hapifhir/org.hl7.fhir.core/issues/1703) / [#1699](https://github.com/hapifhir/org.hl7.fhir.core/issues/1699)

## HAPI-FHIR Validator Cli
* Download validator:
    * `wget https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar`

## Matchbox
* Requires JDK 21 and maven
    * `sudo apt install openjdk-21-jdk`
    * `sudo apt install maven`
* Clone [matchbox](https://github.com/ahdis/matchbox)
```bash
cd ${HOME}
git clone https://github.com/ahdis/matchbox.git
```

# StructureDefinitions
Generate StructureDefinitions (unshorten FSH):
```bash
sushi build
```

# Build Implementation Guide (IG)
```bash
./_updatePublisher.sh
./_genonce.sh
```

# Running transformations using Validator Cli
## Compile maps
```bash
OUT_DIR="temp/map"
mkdir -p ${OUT_DIR}
for f in $(ls maps/*.map) ; do
    BASE=$(basename ${f} .map)
    java -jar validator_cli.jar -ig ${f} \
        -compile http://research.balgrist.ch/fhir2sphn/StructureMap/${BASE} \
        -version 4.0 -output ${OUT_DIR}/${BASE}.xml
done
```

## Execute a transformation
Transform input data ```testdata/pat.json```:
```bash
java -jar validator_cli.jar testdata/pat.json \
    -transform http://research.balgrist.ch/fhir2sphn/StructureMap/BundleToLoopSphn \
    -version 4.0 -ig ${OUT_DIR}/ -ig ./fsh-generated/resources \
    -output temp/result.json
```

## Validate the result
Validate the resulting  ```temp/result.json``` against the LogicalModel:
```bash
java -jar validator_cli.jar temp/result.json \
    -version 4.0 -ig ./fsh-generated/resources
```

# Running transformations using Matchbox
## Run local matchbox server:
```bash
cd matchbox/matchbox-server
mvn clean install -DskipTests spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx4g" \
	-Dspring-boot.run.directories=../../LOOP_FHIR2SPHN/output \
	-Dspring-boot.run.arguments=--spring.config.additional-location=file:../../LOOP_FHIR2SPHN/with-preload/application.yaml
```
Note: After updating the StructureDefinitions, the database needs to be cleared to force re-loading of the IG package (output/package.tgz):
```bash
rm -rf matchbox/matchbox-server/database
```

## Compile maps / execute transformation
* POST maps and exectute transformation using REST against local matchbox server:
    * See [transform.http](transform.http)


# Postprocessing
```bash
cat temp/result.json  | jq 'walk(if type == "object" then with_entries(.key = (if .key == "reference" then "id" else .key end)) else . end)' | jq 'walk(if type == "object" then with_entries(.key = (if .key != "id" and .key != "iri" and .key != "termid" and .key != "content" and .key != "target_concept" then "sphn:" else "" end ) + .key) else . end)'
```

# (Containerized) Testing Framework

An automated test suite verifies that FML mapping rules produce the expected SPHN output. Tests run against a containerized Matchbox server: the framework uploads the `.map` files from the local `maps/` directory, transforms FHIR Bundles, and asserts on the JSON output. This makes the edit-upload-test cycle fast when developing maps.

## Setup

Install Python dependencies (Python 3.10+):
```bash
pip install -r tests/requirements-test.txt
```

Docker is required to run the Matchbox container.

## Development workflow

The recommended workflow for developing and testing maps:

1. Start the Matchbox container once:
```bash
docker compose -f tests/docker-compose.yml up -d
```

2. Edit a `.map` file in `maps/`.

3. Run the relevant tests (maps are re-uploaded automatically at the start of each pytest session):
```bash
pytest tests/maps/test_allergy_intolerance.py -v
```

4. Iterate: edit the map, re-run tests. To force re-upload of maps after changes, start a new pytest session (each session uploads all maps fresh).

5. Run the full suite before committing:
```bash
pytest tests/ -v
```

To stop the container when done:
```bash
docker compose -f tests/docker-compose.yml down
```

## Running all tests without starting the container first

Use the `--start-container` flag to let pytest manage the container lifecycle automatically (starts before tests, stops after):
```bash
pytest tests/ -v --start-container
```

## Test fixtures

The test infrastructure is defined in `tests/conftest.py` and provides the following pytest fixtures:

| Fixture | Scope | Description |
|---|---|---|
| `matchbox_container` | session | Manages the Docker container lifecycle. With `--start-container`, starts/stops the container automatically. Otherwise expects it already running. |
| `matchbox_ready` | session | Waits for the Matchbox server to be healthy (polls `/metadata` endpoint). |
| `maps_uploaded` | session | Runs `sushi build` inside the container, uploads StructureDefinitions, then uploads all `.map` files from `maps/` in dependency order (Utils first, BundleToLoopSphn last). |
| `transform_bundle` | session | Returns a function `transform_bundle(bundle_dict, source_map=None)` that POSTs a FHIR Bundle to the Matchbox `$transform` endpoint and returns the result as a dict. Defaults to `BundleToLoopSphn`. |
| `make_bundle` | function | Factory that creates a FHIR Bundle wrapping one or more resources: `make_bundle(patient, observation, ...)`. |
| `base_patient` | function | A minimal Patient resource with an identifier, for use in bundles that require a patient. |


## Test structure

Tests are organized by map file in `tests/maps/`: Each test constructs a minimal FHIR Bundle, transforms it via Matchbox, and asserts on the resulting SPHN output.

## Coverage verification (mutation testing)

The script `tests/verify_map_coverage.py` checks whether each mapping rule is covered by at least one test. It works by commenting out one rule at a time, re-running the relevant tests, and checking that at least one test fails:

```bash
# Verify coverage for all maps (requires running Matchbox container)
python tests/verify_map_coverage.py

# Verify a specific map
python tests/verify_map_coverage.py --map AllergyIntoleranceToAllergy.map

# Dry run: list all extracted rules without running tests
python tests/verify_map_coverage.py --dry-run
```

The report shows each rule as **COVERED** (a test detected the removal) or **MISSING** (no test failed when the rule was removed).


