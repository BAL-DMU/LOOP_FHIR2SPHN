FROM europe-west6-docker.pkg.dev/ahdis-ch/ahdis/matchbox:v4.0.1
EXPOSE 8080 

# Alpine:
USER root
RUN apk add --no-cache curl wget maven jekyll nodejs npm bash jq \
    fontconfig ttf-dejavu freetype-dev
RUN java --version

# get some sushi
RUN npm install -g fsh-sushi
RUN npm cache clean --force

# Loop & map it as you w(f)ish
USER matchbox
COPY docker/entrypoint.sh /
COPY docker/build_maps.sh /
COPY docker/application.yaml /config/

WORKDIR /home/matchbox/fhir2sphn

COPY ./maps ./maps/
COPY ./input ./input/
COPY ./ig.ini .
COPY ./sushi-config.yaml .
COPY ./_updatePublisher.sh .
COPY ./_genonce.sh .

RUN sushi build
RUN ./_updatePublisher.sh -y
RUN ./_genonce.sh

# purge cache
RUN rm -rf /home/matchbox/.fhir

USER root
WORKDIR /

RUN cp /home/matchbox/fhir2sphn/output/package.tgz /package.tgz
RUN chown -R matchbox:matchbox /package.tgz

USER matchbox
#RUN rm -rf /tmp/fhir2sphn

# Compile maps to load all needed components from the Internet
ENV MAPS_DIR="/home/matchbox/fhir2sphn/maps"


ENTRYPOINT ["/entrypoint.sh"]
CMD ["build"]
