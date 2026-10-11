# Build from the extracted, checksum-verified native release archive directory:
# docker build -f /path/to/psmc-rs/containers/Dockerfile -t psmc-rs:0.8.0 .
# The archive architecture must match the build platform. No genome goes here.
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update \
    && apt-get install -y --no-install-recommends zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY psmc-rs /usr/local/bin/psmc-rs
COPY LICENSE NOTICE.md CITATION.cff /usr/local/share/psmc-rs/
COPY reference/LICENSE.psmc.txt reference/LICENSE.phlash.txt /usr/local/share/psmc-rs/reference/
COPY reference/rust-1.90.0/ /usr/local/share/psmc-rs/reference/rust-1.90.0/
USER 65532:65532
WORKDIR /data
ENTRYPOINT ["/usr/local/bin/psmc-rs"]
