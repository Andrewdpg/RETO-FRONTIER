#!/usr/bin/env bash
# Despliega el servicio en Cloud Run. Idempotente: cada paso revisa el estado y se salta si ya está hecho.
#
#   ./deploy.sh                       # usa el proyecto activo de gcloud
#
# Variables (con su valor por defecto): REGION=us-central1 SERVICE=reemplazo
#   MIN_INSTANCES=1 MAX_INSTANCES=1 CPU=1 MEMORY=512Mi BUDGET_USD=5
# Un solo proceso porque el estado vive en memoria (D1).
# Secreto: TEAM_ENTRYPOINT_TOKEN, leído de ./.env y montado con el mismo nombre. Nunca se imprime.
# El deploy siempre pide confirmación: no hay flag para saltarla.
set -euo pipefail

PROJECT=$(gcloud config get-value project 2>/dev/null)
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-reemplazo}
MIN_INSTANCES=${MIN_INSTANCES:-1}
MAX_INSTANCES=${MAX_INSTANCES:-1}
CPU=${CPU:-1}
MEMORY=${MEMORY:-512Mi}
BUDGET_USD=${BUDGET_USD:-5}
APIS=(run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com billingbudgets.googleapis.com)

ok()   { printf '  \e[32m✓\e[0m %s\n' "$*"; }
skip() { printf '  \e[2m- %s (ya estaba)\e[0m\n' "$*"; }
info() { printf '\n\e[1m%s\e[0m\n' "$*"; }
die()  { printf '\e[31m✗ %s\e[0m\n' "$*" >&2; exit 1; }

[[ -n $PROJECT ]] || die "no hay proyecto activo: gcloud config set project <id>"
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
info "Proyecto $PROJECT · cuenta $ACCOUNT · región $REGION · servicio $SERVICE"

info "1. Facturación"
BILLING=$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)')
[[ $(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)') == True ]] || die "el proyecto no tiene facturación"
ok "habilitada (${BILLING#billingAccounts/})"

info "2. Región por defecto"
if [[ $(gcloud config get-value run/region 2>/dev/null) == "$REGION" ]]; then skip "run/region=$REGION"
else gcloud config set run/region "$REGION" -q >/dev/null; ok "run/region=$REGION"; fi

info "3. APIs"
ENABLED=$(gcloud services list --enabled --format='value(config.name)')
for api in "${APIS[@]}"; do
  if grep -qx "$api" <<<"$ENABLED"; then skip "$api"
  else gcloud services enable "$api" -q; ok "$api"; fi
done

info "4. Alerta de presupuesto (US\$$BUDGET_USD; avisa por correo, no corta el gasto)"
BUDGET_NAME="$SERVICE-$PROJECT"
if gcloud billing budgets list --billing-account="${BILLING#billingAccounts/}" --format='value(displayName)' | grep -qx "$BUDGET_NAME"; then
  skip "$BUDGET_NAME"
else
  gcloud billing budgets create --billing-account="${BILLING#billingAccounts/}" --display-name="$BUDGET_NAME" \
    --budget-amount="${BUDGET_USD}USD" --filter-projects="projects/$PROJECT" \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 -q >/dev/null
  ok "$BUDGET_NAME: avisos al 50%, 90% y 100%"
fi

info "5. Repositorio de imágenes"
if gcloud artifacts repositories describe cloud-run-source-deploy --location="$REGION" >/dev/null 2>&1; then skip "cloud-run-source-deploy"
else gcloud artifacts repositories create cloud-run-source-deploy --repository-format=docker --location="$REGION" -q; ok "cloud-run-source-deploy"; fi

info "6. Secretos"
RUNTIME_SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
SECRETS=()
put_secret() {  # nombre, valor (vacío = no tocar)
  local name=$1 value=$2
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    if [[ -n $value && $value != "$(gcloud secrets versions access latest --secret="$name" 2>/dev/null)" ]]; then
      printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- -q >/dev/null; ok "$name: versión nueva"
    else skip "$name"; fi
  elif [[ -n $value ]]; then
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --replication-policy=automatic -q >/dev/null; ok "$name: creado"
  else
    printf '  ! %s no existe y no lo pasaste: el servicio arranca sin él\n' "$name"; return
  fi
  if gcloud secrets get-iam-policy "$name" --format=json | grep -q "serviceAccount:$RUNTIME_SA"; then skip "$name: acceso del servicio"
  else gcloud secrets add-iam-policy-binding "$name" --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor -q >/dev/null; ok "$name: acceso del servicio"; fi
  SECRETS+=("$name=$name:latest")
}
# El secreto viejo TEAM_TOKEN tenía otro valor: este nombre nuevo evita heredarlo.
TEAM_ENTRYPOINT_TOKEN=$(sed -n 's/^TEAM_ENTRYPOINT_TOKEN=//p' .env 2>/dev/null | tail -n1 | tr -d "\"'\r")
[[ -n $TEAM_ENTRYPOINT_TOKEN ]] || die "falta TEAM_ENTRYPOINT_TOKEN en ./.env"
put_secret TEAM_ENTRYPOINT_TOKEN "$TEAM_ENTRYPOINT_TOKEN"

info "7. Deploy"
CURRENT=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url,status.latestReadyRevisionName)' 2>/dev/null || true)
if [[ -n $CURRENT ]]; then
  read -r URL REV <<<"$CURRENT"
  printf '  REDEPLOY de %s\n  revisión actual: %s\n  URL: %s\n' "$SERVICE" "$REV" "$URL"
else
  printf '  DEPLOY NUEVO de %s (todavía no existe)\n' "$SERVICE"
fi
printf '  código: %s · instancias %s-%s · %s CPU · %s\n' "$PWD" "$MIN_INSTANCES" "$MAX_INSTANCES" "$CPU" "$MEMORY"
read -r -p "  ¿Confirmás? [s/N] " answer
[[ $answer == [sS] ]] || die "cancelado"

SECRET_FLAG=()
((${#SECRETS[@]})) && SECRET_FLAG=(--set-secrets="$(IFS=,; echo "${SECRETS[*]}")")
gcloud run deploy "$SERVICE" --source . --region="$REGION" --allow-unauthenticated --port=8080 \
  --min-instances="$MIN_INSTANCES" --max-instances="$MAX_INSTANCES" --cpu="$CPU" --memory="$MEMORY" \
  "${SECRET_FLAG[@]}" -q

URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
info "8. Verificación"
# /health pide token (log 53). El header va por stdin para que el token no aparezca en la lista de procesos.
if printf 'Authorization: Bearer %s\n' "$TEAM_ENTRYPOINT_TOKEN" | curl -fsS --max-time 20 -H @- "$URL/health" >/dev/null; then ok "$URL/health responde"; else die "$URL/health no responde"; fi
printf '\nEntrypoint: %s\n' "$URL"
