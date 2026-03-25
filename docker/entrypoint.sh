#!/bin/bash

echo "LOOP-FHIR2SPHN entrypoint"


if [[ "$1" = "build" ]]; then
    echo "Running java matchbox, and building and upload FHIR2SPHN mappings..."
    /build_maps.sh &
    java -Xmx8g -jar /matchbox.jar -Dspring.config.additional-location=optional:file:/config/application.yaml,optional:file:application.yaml
elif [[ "$1" = "debug" ]]; then
    echo "Running java matchbox in java debug mode on port 5005..."
    # debug log
    # -Dspring-boot.run.arguments="--debug"
    # --debug
    java -Xmx3072M -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar /matchbox.jar -Dspring.config.additional-location=optional:file:/config/application.yaml,optional:file:application.yaml
else # -: run
    echo "Running java matchbox..."
    java -Xmx8g -jar /matchbox.jar -Dspring.config.additional-location=optional:file:/config/application.yaml,optional:file:application.yaml
fi

