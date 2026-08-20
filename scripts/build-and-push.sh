#!/usr/bin/env bash
#
# Build the application image and push it to Artifact Registry.
#
# One image holds both runtimes. Which one starts is a command, not a build, so
# the webhook and the worker deploy the same digest.
#
#   scripts/build-and-push.sh
#   PROJECT_ID=... REGION=... TAG=... scripts/build-and-push.sh
#   scripts/build-and-push.sh --no-push        build only, push nothing
#
# The tag is the short commit by default, and gains a "-dirty" suffix when the
# working tree has uncommitted changes, so a tag never claims to be a commit it
# is not. "latest" moves with each push; deploy the commit tag, not that one.
#
# The registry itself comes from scripts/provision-dev.sh.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-build-ai-systems-dev}"
REGION="${REGION:-europe-west1}"
AR_REPOSITORY="${AR_REPOSITORY:-support-agent}"
IMAGE_NAME="${IMAGE_NAME:-support-agent}"

# Cloud Run runs x86-64. An Apple Silicon machine builds arm64 by default, and
# that image starts locally and then fails to start in Cloud Run.
PLATFORM="${PLATFORM:-linux/amd64}"

REGISTRY_HOST="${REGION}-docker.pkg.dev"
IMAGE_PATH="${REGISTRY_HOST}/${PROJECT_ID}/${AR_REPOSITORY}/${IMAGE_NAME}"

push=true
case "${1:-}" in
  --no-push) push=false ;;
  "") ;;
  *) printf 'usage: %s [--no-push]\n' "$0" >&2; exit 2 ;;
esac

step() { printf '\n== %s\n' "$1"; }
ok() { printf '   %s\n' "$1"; }
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }

resolve_tag() {
  if [[ -n "${TAG:-}" ]]; then
    printf '%s' "$TAG"
    return
  fi
  local commit suffix=""
  commit="$(git -C "$repo_root" rev-parse --short HEAD)" || fail "not a git repository"
  git -C "$repo_root" diff --quiet HEAD -- || suffix="-dirty"
  printf '%s%s' "$commit" "$suffix"
}

require_tools() {
  command -v docker >/dev/null 2>&1 || fail "docker is not installed"
  docker info >/dev/null 2>&1 || fail "docker is not running"
  if [[ "$push" == true ]]; then
    command -v gcloud >/dev/null 2>&1 || fail "gcloud is not installed"
    gcloud --quiet auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
      || fail "no active gcloud account. Run: gcloud auth login"
  fi
}

require_registry() {
  step "Artifact Registry"
  gcloud --quiet artifacts repositories describe "$AR_REPOSITORY" \
    --project "$PROJECT_ID" --location "$REGION" >/dev/null 2>&1 \
    || fail "no repository ${AR_REPOSITORY} in ${PROJECT_ID}/${REGION}. Run: scripts/provision-dev.sh"
  ok "${IMAGE_PATH}"

  # Registry credentials are a per-machine Docker setting, so only write it
  # when this host has not been pointed at this registry before.
  if docker-credential-gcloud list 2>/dev/null | grep -q "$REGISTRY_HOST"; then
    ok "docker is already authenticated to ${REGISTRY_HOST}"
  else
    ok "authenticating docker to ${REGISTRY_HOST}"
    gcloud --quiet auth configure-docker "$REGISTRY_HOST" >/dev/null
  fi
}

build_image() {
  step "Build"
  ok "platform ${PLATFORM}"
  ok "tag      ${tag}"
  docker build \
    --platform "$PLATFORM" \
    --tag "${IMAGE_PATH}:${tag}" \
    --tag "${IMAGE_PATH}:latest" \
    --file "${repo_root}/Dockerfile" \
    "$repo_root"
}

push_image() {
  step "Push"
  docker push "${IMAGE_PATH}:${tag}"
  docker push "${IMAGE_PATH}:latest"
}

summary() {
  step "Done"
  local digest
  digest="$(gcloud --quiet artifacts docker images describe "${IMAGE_PATH}:${tag}" \
    --project "$PROJECT_ID" --format='value(image_summary.digest)' 2>/dev/null || true)"
  ok "image   ${IMAGE_PATH}:${tag}"
  [[ -n "$digest" ]] && ok "digest  ${digest}"
  printf '\nThe webhook and the worker run this same image:\n'
  printf '  uvicorn support_agent_app.api.main:create_app    --factory --host 0.0.0.0 --port 8080\n'
  printf '  uvicorn support_agent_app.worker.main:create_app --factory --host 0.0.0.0 --port 8080\n'
}

main() {
  tag="$(resolve_tag)"
  require_tools
  if [[ "$push" == true ]]; then
    require_registry
    build_image
    push_image
    summary
  else
    build_image
    step "Done"
    ok "built ${IMAGE_PATH}:${tag}, not pushed"
  fi
}

main
