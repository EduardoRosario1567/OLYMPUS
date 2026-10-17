# Qualification template: build only in an approved provisioning environment.
# Execution resolves the locally built image to its immutable sha256 ID.
# No automatic pull/build/install occurs inside Olympus missions.
ARG RUNNER_BASE
FROM ${RUNNER_BASE}
LABEL org.olympus.project-runner="v1"
# Required by the existing zsh -n project validation contract.
RUN apt-get update \
 && apt-get install --no-install-recommends -y zsh \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir pytest==8.3.5
USER 65534:65534
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
ENTRYPOINT ["python3"]
