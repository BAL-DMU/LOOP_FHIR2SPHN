# LOOP BMIP FHIR to SPHN Mapping

FHIR to SPHN mappings for LOOP BMIP using [FHIR Mapping Language (FML)](https://build.fhir.org/mapping-language.html)
* Mappings: [maps](maps/)

StructureDefinitions for the target LOOP schema is defined using [FHIR Shorthand (FSH)](https://build.fhir.org/ig/HL7/fhir-shorthand/)
* FSH: [input/fsh/LogicalModel.fsh](input/fsh/LogicalModel.fsh)

## Installation
* Install SUSHI from https://github.com/FHIR/sushi
* For building the IG, jekyll is required: ```sudo apt install jekyll```

## StructureDefinitions
Generate StructureDefinitions (unshorten FSH):
```bash
sushi build
```

## Compile maps
```bash
mkdir -p temp/map
for f in $(ls maps/*.map) ; do
    BASE=$(basename ${f} .map)
    java -jar temp/validator_cli.jar -ig ${f} -compile http://research.balgrist.ch/fhir2sphn/StructureMap/${BASE} -version 4.0 -output temp/map/${BASE}.xml
done
```

## Execute a transformation
Transform input data ```testdata/pat.json```:
```bash
java -jar temp/validator_cli.jar testdata/pat.json -transform http://research.balgrist.ch/fhir2sphn/StructureMap/BundleToLoopSphn -version 4.0 -ig temp/map/ -ig ./fsh-generated/resources -output temp/result.json
```

Postprocessing:
```bash
cat temp/result.json  | jq 'walk(if type == "object" then with_entries(.key = (if .key == "reference" then "id" else .key end)) else . end)' | jq 'walk(if type == "object" then with_entries(.key = (if .key != "id" and .key != "iri" and .key != "termid" and .key != "content" then "sphn:" else "" end ) + .key) else . end)'
```

## Build Implementation Guide (IG)
```bash
./_updatePublisher.sh
./_genonce.sh
```
