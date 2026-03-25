FROM europe-west6-docker.pkg.dev/ahdis-ch/ahdis/matchbox:v4.0.1
EXPOSE 8080 

# invalidate chache
RUN ls

# Alpine:
USER root
RUN apk update
RUN apk add curl
RUN apk add wget
RUN apk add maven
RUN apk add git
RUN apk add jekyll
RUN apk add nodejs npm
RUN apk add bash
RUN apk add jq

# RUN apk add openjdk21
# RUN apk add font-dejavu
RUN apk add --no-cache fontconfig ttf-dejavu freetype-dev # && /usr/glibc/sbin/ldconfig
RUN java --version

# get some sushi
RUN npm install -g fsh-sushi

RUN apk --purge del


# Loop & map it as you w(f)ish
USER matchbox
COPY docker/entrypoint.sh /
COPY docker/build_maps.sh /
COPY docker/application.yaml /config/

ENV LOOP_FHIR2SPHN_COMMIT_HASH=5563371e81cb20a082bc2f8f84b62bb4b60699b1
RUN git clone https://github.com/BAL-DMU/LOOP_FHIR2SPHN.git /home/matchbox/fhir2sphn && \
    cd /home/matchbox/fhir2sphn && \
    git checkout $LOOP_FHIR2SPHN_COMMIT_HASH


WORKDIR /home/matchbox/fhir2sphn
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
ENV COMPILED_DIR="/home/matchbox/fhir2sphn/maps/compiled"


ENTRYPOINT ["/entrypoint.sh"]
CMD ["build"]
