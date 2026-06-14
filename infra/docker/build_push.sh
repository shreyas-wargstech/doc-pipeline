#!/usr/bin/env bash
# Build all Lambda container images and push to ECR.
# Usage (from repo root): AWS_ACCOUNT_ID=<id> ./infra/docker/build_push.sh [image_tag]
set -euo pipefail

ACCOUNT="${AWS_ACCOUNT_ID:?Must set AWS_ACCOUNT_ID}"
REGION="${AWS_REGION:-ap-south-1}"
ENV="${ENVIRONMENT:-dev}"
TAG="${1:-latest}"

REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
PREFIX="docintel-${ENV}"

echo "==> Authenticating with ECR"
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${REGISTRY}"

build_and_push() {
  local name="$1"
  local dockerfile="infra/docker/Dockerfile.${name}"
  local repo="${REGISTRY}/${PREFIX}/${name}"
  echo ""
  echo "==> Building ${name} (${dockerfile})"
  docker build -f "${dockerfile}" -t "${repo}:${TAG}" .
  echo "==> Pushing ${repo}:${TAG}"
  docker push "${repo}:${TAG}"
}

# Build order: light first (fastest sanity check), then ingest, ocr, persist-index last
build_and_push "light"
build_and_push "ingest"
build_and_push "ocr"
build_and_push "persist-index"

echo ""
echo "==> All images pushed to ECR with tag: ${TAG}"
echo "Next: terraform apply with ecr_image_tag=${TAG}"
