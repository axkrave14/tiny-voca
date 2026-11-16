#!/usr/bin/env bash
# Execute only after selecting the Google Cloud project and accepting its usage costs.
set -euo pipefail
PROJECT="${1:?Usage: bash voice_studio/deploy-cloudrun.sh PROJECT_ID [REGION]}"
REGION="${2:-asia-southeast1}"
cd "$(dirname "$0")/.."
gcloud run deploy tiny-voca-studio \
  --project "$PROJECT" --region "$REGION" --source . \
  --no-allow-unauthenticated --cpu 2 --memory 2Gi \
  --concurrency 1 --min-instances 0 --max-instances 1 --timeout 300
printf '\nDeployment finished. Open through an authenticated local proxy:\n'
printf 'gcloud run services proxy tiny-voca-studio --project %q --region %q --port 8090\n' "$PROJECT" "$REGION"
