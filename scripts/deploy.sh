#!/usr/bin/env bash
set -euo pipefail

subscription_id="${1:?subscription id required}"
resource_group="${2:?resource group required}"
location="${3:-eastus2}"

az account set --subscription "$subscription_id"
az group create --name "$resource_group" --location "$location" --output none
read -r -s -p "PostgreSQL admin password: " postgres_password
echo

deployment_json="$(az deployment group create --resource-group "$resource_group" --template-file infra/main.bicep --parameters postgresAdminPassword="$postgres_password" --query properties.outputs -o json)"
unset postgres_password

storage_name="$(jq -r '.storageAccountName.value' <<<"$deployment_json")"
api_name="$(jq -r '.apiName.value' <<<"$deployment_json")"
api_url="$(jq -r '.apiUrl.value' <<<"$deployment_json")"
storage_key="$(az storage account keys list --resource-group "$resource_group" --account-name "$storage_name" --query '[0].value' -o tsv)"

archive_dir=""
if [[ "${SKIP_API_DEPLOY:-false}" != "true" ]]; then
	archive_dir="$(mktemp -d /tmp/asistente-api.XXXXXX)"
	archive_path="$archive_dir/api.zip"
	(cd backend && zip -qr "$archive_path" app requirements.txt)
	az webapp deploy --resource-group "$resource_group" --name "$api_name" --src-path "$archive_path" --type zip --output none
fi

cp frontend/config.example.js frontend/config.js
printf 'window.ASISTENTE_CONFIG = { apiUrl: "%s" };\n' "$api_url" > frontend/config.js
az storage blob service-properties update --account-name "$storage_name" --account-key "$storage_key" --static-website --index-document index.html --404-document index.html --output none
az storage blob upload-batch --account-name "$storage_name" --account-key "$storage_key" --destination '$web' --source frontend --overwrite --output none
if [[ -n "$archive_dir" ]]; then
	rm -rf "$archive_dir"
fi
rm -f frontend/config.js

jq . <<<"$deployment_json"

