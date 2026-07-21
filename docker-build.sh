#!/usr/bin/env bash
# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# imap-mcp-server — Docker Build Script (PS-91 / PS-97 v1.1 §1.1.3)
# Uses BuildKit secret mount for optional package-index credentials; credentials never enter image layers.
#
# Variant selector (PS-97 v1.1 §1.1.3):
#   --variant public  (default) builds Dockerfile.public for publication
#   --variant dev     builds Dockerfile (internal/dev) when present in a developer checkout
#
# Usage:
#   docker-build.sh [VERSION] [--variant dev|public]
#
# Env overrides still apply (PIP_INDEX_URL, CUSTOM_CA_CERT, etc.). The --variant flag
# selects which Dockerfile is fed to BuildKit.
set -euo pipefail

# ── Argument parsing ────────────────────────────────────────────
VARIANT="${PUBLICATION_BUILD_VARIANT:-public}"
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --variant)
      VARIANT="${2:-dev}"
      shift 2
      ;;
    --variant=*)
      VARIANT="${1#*=}"
      shift
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
set -- "${POSITIONAL[@]}"

case "${VARIANT}" in
  public) DOCKERFILE="Dockerfile.public" ;;
  dev)    DOCKERFILE="Dockerfile" ;;
  *)
    echo "ERROR: --variant must be 'dev' or 'public' (got: ${VARIANT})" >&2
    exit 2
    ;;
esac

# W28A-SEC-R17: no hardcoded internal registry base image. Default to the public
# upstream base; the build environment may override PYTHON_BASE_IMAGE (e.g. a dev
# build supplying an internal registry.<host>/python-runtime reference).
PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE:-python:3.13-slim}"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "ERROR: ${DOCKERFILE} not found (variant=${VARIANT})" >&2
  exit 2
fi

VERSION="${1:-latest}"
CONTAINER="imap-mcp-server"
FOLDER="cloud-dog"
REGISTRY="${REGISTRY:-}"
PIP_CONF=".pip.conf.build"
CA_BUNDLE_FILE=".ca-bundle.build"

PUBLICATION_TAG_SUFFIX="${PUBLICATION_TAG_SUFFIX:-}"
if [[ -n "${PUBLICATION_TAG_SUFFIX}" ]]; then
  if [[ ! "${PUBLICATION_TAG_SUFFIX}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
    echo "ERROR: PUBLICATION_TAG_SUFFIX must match ^[a-z0-9]([a-z0-9-]*[a-z0-9])?\$ (got: '${PUBLICATION_TAG_SUFFIX}')" >&2
    exit 2
  fi
  case "${PUBLICATION_TAG_SUFFIX}" in
    latest|dev|prod|release|stable)
      echo "ERROR: PUBLICATION_TAG_SUFFIX '${PUBLICATION_TAG_SUFFIX}' is reserved" >&2
      exit 2
      ;;
  esac
  EFFECTIVE_TAG="${VERSION}-${PUBLICATION_TAG_SUFFIX}"
  echo "Publication test build: tag suffix '-${PUBLICATION_TAG_SUFFIX}' (registry tag will be skipped)."
else
  EFFECTIVE_TAG="${VERSION}"
fi

# CA sources (any that exist will be merged in this order)
CUSTOM_CA_CERT="${CUSTOM_CA_CERT:-}"
CORPORATE_CA_CERT="${CORPORATE_CA_CERT:-/usr/local/share/ca-certificates/cloud-dog.net.ca.crt}"
ACME_CA_CERT="${ACME_CA_CERT:-}"

echo "=========================================="
echo "Docker Build: ${FOLDER}/${CONTAINER}:${EFFECTIVE_TAG} (variant=${VARIANT}, dockerfile=${DOCKERFILE})"
echo "=========================================="

# W28A-SEC-R17: adopt git-mcp's shape — REGISTRY defaults to empty (see above);
# only prefix the internal registry when the build environment supplies it. No
# hardcoded registry.<host> default reaches the committed source.
if [[ "${VARIANT}" == "dev" && -n "${REGISTRY}" ]]; then
  IMAGE_REF="${REGISTRY}/${FOLDER}/${CONTAINER}:${EFFECTIVE_TAG}"
else
  IMAGE_REF="${FOLDER}/${CONTAINER}:${EFFECTIVE_TAG}"
fi

# ── PyPI Configuration (PS-97 v1.1 §4 / §3.3 strict-single-index) ─
# The active package index is supplied by the build environment:
#   public boundary (GitHub/GHCR): pypi.org/simple — platform packages
#       resolve from the public Cloud-Dog-External namespace or from
#       GitHub-mirrored source. (default for --variant public)
#   gitea staging boundary:        set PIP_INDEX_URL to the Gitea public PyPI
#       index via the caller's environment (PIP_INDEX_URL=...).
# Never hardcode an internal host here and never use a second index
# (a fallback index is forbidden by PS-97 §3.3 + §4 — single index-url only).
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  : # honour caller override (e.g. Gitea staging boundary)
else
  PIP_INDEX_URL="https://pypi.org/simple"
fi
PYPI_USERNAME="${PYPI_USERNAME:-}"
PYPI_PASSWORD="${PYPI_PASSWORD:-}"

# Generate pip.conf — with auth if credentials available, without if not
if [[ -n "${PYPI_USERNAME}" ]] && [[ -n "${PYPI_PASSWORD}" ]]; then
  cat > "${PIP_CONF}" << EOF
[global]
index-url = https://${PYPI_USERNAME}:${PYPI_PASSWORD}@${PIP_INDEX_URL#https://}
trusted-host = $(python3 -c "from urllib.parse import urlsplit; print(urlsplit('${PIP_INDEX_URL}').hostname or 'pypi.org')")
EOF
  echo "pip.conf generated with authenticated PyPI access (strict-single-index, PS-97 §3.5)."
else
  echo "NOTE: No PYPI credentials set — using anonymous access."
  cat > "${PIP_CONF}" << EOF
[global]
index-url = ${PIP_INDEX_URL}
trusted-host = $(python3 -c "from urllib.parse import urlsplit; print(urlsplit('${PIP_INDEX_URL}').hostname or 'pypi.org')")
EOF
  echo "pip.conf generated with anonymous PyPI access (strict-single-index, PS-97 §3.5)."
fi
chmod 600 "${PIP_CONF}"

# ── CA Certificate ───────────────────────────────────────────────
rm -f "${CA_BUNDLE_FILE}"
touch "${CA_BUNDLE_FILE}"
for cert in "${CUSTOM_CA_CERT}" "${CORPORATE_CA_CERT}" "${ACME_CA_CERT}"; do
  if [[ -n "${cert}" && -f "${cert}" ]]; then
    cat "${cert}" >> "${CA_BUNDLE_FILE}"
    echo "" >> "${CA_BUNDLE_FILE}"
  fi
done
chmod 600 "${CA_BUNDLE_FILE}"

# ── Build ────────────────────────────────────────────────────────
# ── W28C-1719 publish-before-pin guard + build-provenance revision label (fail-closed) ──
_PBP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# W28A-SEC-R18: the publish-before-pin guard is INTERNAL CI build-guard tooling
# (it resolves internal cloud-dog-* pins from the single internal index) and is
# intentionally excluded from the public source mirror. Run it only when present
# (internal developer checkout); the public/anonymous build has no internal pins
# to guard, so its absence must not fail the hermetic public build.
if [[ -x "${_PBP_DIR}/scripts/publish-before-pin-guard.sh" ]]; then
  "${_PBP_DIR}/scripts/publish-before-pin-guard.sh" "${_PBP_DIR}" || exit $?
fi
_PBP_REV="$(git -C "${_PBP_DIR}" rev-parse HEAD 2>/dev/null || echo unknown)"
# W28E-1863 fix-wave-d (WSC-014): propagate build identity to the image so the
# Dockerfile can stamp OCI labels + runtime ENV for build_identity() / /version.
SOURCE_COMMIT="${_PBP_REV}"
SOURCE_BRANCH="$(git -C "${_PBP_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

DOCKER_BUILDKIT=1 docker buildx build \
  --label "org.opencontainers.image.revision=${_PBP_REV}" \
  --progress=plain \
  --network=host \
  --load \
  -f "${DOCKERFILE}" \
  --secret id=pip_conf,src="${PIP_CONF}" \
  --secret id=ca_bundle,src="${CA_BUNDLE_FILE}" \
  --build-arg HTTP_PROXY="${HTTP_PROXY:-}" \
  --build-arg HTTPS_PROXY="${HTTPS_PROXY:-}" \
  --build-arg NO_PROXY="${NO_PROXY:-}" \
  --build-arg http_proxy="${http_proxy:-}" \
  --build-arg https_proxy="${https_proxy:-}" \
  --build-arg no_proxy="${no_proxy:-}" \
  --build-arg SOURCE_COMMIT="${SOURCE_COMMIT}" \
  --build-arg SOURCE_BRANCH="${SOURCE_BRANCH}" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --build-arg PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE}" \
  -t "${IMAGE_REF}" \
  . 2>&1 | tee docker-build.log

BUILD_STATUS=${PIPESTATUS[0]}

if [[ ${BUILD_STATUS} -eq 0 ]]; then
  echo "Build OK: ${IMAGE_REF} (variant=${VARIANT})"
  if [[ -n "${PUBLICATION_TAG_SUFFIX}" ]]; then
    echo "Registry tag skipped for publication suffix '${PUBLICATION_TAG_SUFFIX}'."
  elif [[ "${VARIANT}" == "dev" ]]; then
    echo "Internal registry reference ready: ${IMAGE_REF}"
  else
    echo "Public variant built; internal registry tag skipped (PS-97 §1.1.3 closed-loop)."
  fi
else
  echo "Build FAILED — see docker-build.log"
fi

# ── Cleanup secrets ──────────────────────────────────────────────
rm -f "${PIP_CONF}" "${CA_BUNDLE_FILE}"
exit ${BUILD_STATUS}
