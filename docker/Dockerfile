FROM europe-west6-docker.pkg.dev/ahdis-ch/ahdis/matchbox:v4.0.1
EXPOSE 8080 

# Alpine:
USER root
RUN apk add --no-cache  --no-check-certificate curl wget maven jekyll nodejs npm bash jq \
    fontconfig ttf-dejavu freetype-dev ca-certificates
RUN java --version

# Optional corporate proxy CA: drop your PEM cert at docker/ca.crt to make curl/wget
# AND the Java IG Publisher trust an SSL-intercepting corporate network. Without it the
# publisher fails with: PKIX path building failed (certificate_unknown). When ca.crt is
# absent the Dockerfile anchor keeps the COPY from failing and the block is a no-op.
COPY docker/Dockerfile docker/ca.cr[t] /tmp/cabuild/
# Always create the file NODE_EXTRA_CA_CERTS points at (stays empty if no proxy CA).
RUN install -m 0644 /dev/null /usr/local/share/ca-certificates/corp-ca.crt && \
    if [ -f /tmp/cabuild/ca.crt ]; then \
      cp /tmp/cabuild/ca.crt /usr/local/share/ca-certificates/corp-ca.crt && \
      update-ca-certificates && \
      JH=$(dirname $(dirname $(readlink -f $(which java)))) && \
      keytool -importcert -noprompt -trustcacerts -alias corp-ca \
        -file /tmp/cabuild/ca.crt -keystore "$JH/lib/security/cacerts" -storepass changeit ; \
    fi && rm -rf /tmp/cabuild

# Node ignores the system trust store, so point it at the (possibly empty) proxy CA
# instead of disabling TLS verification. Covers npm, sushi and the IG Publisher's node calls.
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/corp-ca.crt

# get some sushi
RUN npm install -g fsh-sushi && rm -rf /home/matchbox/.npm

# Loop & map it as you w(f)ish
USER matchbox
COPY docker/entrypoint.sh /
COPY docker/build_maps.sh /
COPY docker/application.yaml /config/

WORKDIR /home/matchbox/fhir2sphn
COPY ./ig.ini .
COPY ./sushi-config.yaml .
COPY ./_updatePublisher.sh .
COPY ./_genonce.sh .
COPY ./maps ./maps/
COPY ./input ./input/


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
