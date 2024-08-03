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
* POST maps and execture transformation using REST against local matchbox server:
    * See [transform.http](transform.http)


# Postprocessing
```bash
cat temp/result.json  | jq 'walk(if type == "object" then with_entries(.key = (if .key == "reference" then "id" else .key end)) else . end)' | jq 'walk(if type == "object" then with_entries(.key = (if .key != "id" and .key != "iri" and .key != "termid" and .key != "content" and .key != "target_concept" then "sphn:" else "" end ) + .key) else . end)'
```


