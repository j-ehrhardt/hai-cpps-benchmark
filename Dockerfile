# HAI-CPPS v2.2 campaign image.
# The official minimal image supplies the OpenModelica command-line compiler;
# this stage adds the Python export/validation environment and this repository.
FROM openmodelica/openmodelica:v1.25.5-minimal

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    CONDA_DIR=/opt/conda \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# A generated Modelica simulation is compiled as C, so the compiler toolchain
# is required at runtime as well as while the image is built.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bzip2 \
        build-essential \
        ca-certificates \
        curl \
        omlibrary \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN case "${TARGETARCH}" in \
        amd64) conda_arch=x86_64 ;; \
        arm64) conda_arch=aarch64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --silent --show-error \
        "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${conda_arch}.sh" \
        --output /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p "${CONDA_DIR}" \
    && rm /tmp/miniconda.sh \
    && "${CONDA_DIR}/bin/conda" clean --all --yes

ENV PATH="/opt/conda/envs/hai-cps/bin:/opt/conda/bin:${PATH}"

# Keep the environment layer independent of application-code edits.
COPY requirements.txt /tmp/requirements.txt
RUN "${CONDA_DIR}/bin/conda" tos accept --override-channels \
        --channel https://repo.anaconda.com/pkgs/main \
    && "${CONDA_DIR}/bin/conda" tos accept --override-channels \
        --channel https://repo.anaconda.com/pkgs/r \
    && "${CONDA_DIR}/bin/conda" create --yes --name hai-cps python=3.12 pip \
    && "${CONDA_DIR}/envs/hai-cps/bin/python" -m pip install --no-cache-dir \
        -r /tmp/requirements.txt \
    && "${CONDA_DIR}/bin/conda" clean --all --yes \
    && rm /tmp/requirements.txt

WORKDIR /opt/hai-cpps
COPY code/ ./code/
COPY models/ ./models/
COPY LICENSE requirements.txt ./

RUN useradd --create-home --shell /bin/bash hai-cpps \
    && mkdir --parents /work/output /work/build \
    && chown --recursive hai-cpps:hai-cpps /work

USER hai-cpps
ENV HOME=/home/hai-cpps
WORKDIR /opt/hai-cpps
VOLUME ["/work"]

# Initialise the cached Modelica Standard Library for the non-root runtime
# user. The generated plant explicitly requires Modelica 4.0.0.
RUN printf 'loadModel(Modelica, {"4.0.0"});\ngetErrorString();\n' \
        > /tmp/load-modelica.mos \
    && omc /tmp/load-modelica.mos \
    | grep --fixed-strings --line-regexp true

ENTRYPOINT ["python", "code/campaign.py"]
CMD ["--config", "code/benchmark_setup.json", "--output", "/work/output/v2.2-ramped", "--build-root", "/work/build/v2.2-ramped", "--jobs", "4"]
