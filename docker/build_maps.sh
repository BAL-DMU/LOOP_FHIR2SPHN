#!/bin/bash

echo "Running build-time commands..."
URL="http://localhost:8080/matchboxv3/fhir"

# wait for port to become available
echo -n "Waiting for matchbox"
while ! nc -z localhost 8080 ; do sleep 1 ; echo -n "." ; done
echo "Matchbox RUNNING"

# Compile/Upload Maps
for i in $(ls ${MAPS_DIR}/*.map) ; do
  echo "Uploading $i"
  curl 	--request POST \
    --fail \
    --url ${URL}/StructureMap \
    --header 'Accept: application/fhir+json;fhirVersion=4.0' \
    --header 'Content-Type: text/fhir-mapping' \
    --data-binary @$i || exit 1
done

echo "Maps upload DONE"
# exit 0
