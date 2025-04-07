#!/bin/bash

# Upload/compile all maps and then 
# transform all data in testdata
# 
# Compare out-ref to out-new:
# 	diff --ignore-matching-lines='"id"\s:' --ignore-matching-lines='"reference"\s:' -r temp/out-ref temp/out-new

URL="http://localhost:8080/matchboxv3/fhir"

if [ $# -lt 1 ] ; then
	echo "Usage: $0 output-dir"
	exit 1
fi
OUT_DIR=$1
mkdir -p ${OUT_DIR}

# wait for port to become available
echo -n "Waiting for matchbox"
while ! nc -z localhost 8080 ; do sleep 1 ; echo -n "." ; done
echo " DONE"

# Upload all SD
#for i in $(ls output/StructureDefinition-*.json) ; do
#	echo $i
#	curl 	--request POST \
#		--fail \
#		--url ${URL}/StructureDefinition \
#		--header 'Accept: application/fhir+xml;fhirVersion=4.0' \
#		--header 'Content-Type: application/fhir+json;fhirVersion=4.0' \
#		--data-binary @$i || exit 1
#done


# Compile/Upload Maps
for i in $(ls maps/*.map) ; do
	echo "Uploading $i"
	curl 	--request POST \
		--fail \
		--url ${URL}/StructureMap \
		--header 'Accept: application/fhir+json;fhirVersion=4.0' \
		--header 'Content-Type: text/fhir-mapping' \
		--data-binary @$i || exit 1
done

# Transform testdata
for i in $(ls testdata/*.json) ; do
	echo "Transforming $i"
	FNAME=$(basename $i .json)
	curl 	--request POST \
		--fail \
		--url "${URL}/StructureMap/\$transform?source=http://research.balgrist.ch/fhir2sphn/StructureMap/BundleToLoopSphn" \
		--header 'Accept: application/fhir+json;fhirVersion=4.0' \
		--header 'Content-Type: application/fhir+json;fhirVersion=4.0' \
		--data @$i -o ${OUT_DIR}/result_${FNAME}.json  || exit 1
done


