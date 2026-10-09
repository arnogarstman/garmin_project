# Infrastructure (Azure)

Two environments built from the same Terraform module:

- **demo**: public. The simulated athlete from `uv run synthesize`, a public dashboard, and no paid AI features.
- **prod**: private. Your own Garmin data, behind Entra ID sign-in, with the AI features on.

Everything runs in **West Europe** (Netherlands), inside the EU Data Boundary.

```
                     GitHub Actions (OIDC, no stored cloud keys)
                       │ build, scan, push          │ terraform apply
                       ▼                            ▼
              Container Registry ───────► one environment (demo or prod)
                                         ┌──────────────────────────────────────────────┐
  Garmin Connect ◄── Container Apps job ─┤ daily, 04:00 UTC: `pipeline` (Dagster)      │
                     (managed identity)  │   raw/  NDJSON per endpoint/load_date (bronze)│
                           │             │   dbt build + tests + checks (silver, gold)   │
                           ▼             │   publish warehouse.duckdb                    │
                   Data Lake Storage ────┤ raw/ · warehouse/ · app/                      │
                           ▲             │                                              │
  You ──► Entra ID ──► Container App ────┤ Streamlit dashboard, read-only warehouse copy │
          (prod only)  (scales to zero)  │ Key Vault: Garmin tokens, Anthropic key      │
                                         │ Log Analytics + alerts → e-mail              │
                                         └──────────────────────────────────────────────┘
```

## Layout

| Path | Contents |
|---|---|
| `bootstrap/` | Applied once, by hand, with local state. Contains the state storage, the container registry, the GitHub OIDC identities, and the dashboard's app registration. |
| `modules/stack/` | One complete environment, composed from the modules below. |
| `modules/storage/` | ADLS Gen2 account with the `raw`, `warehouse` and `app` containers. Has lifecycle tiering and access logs. |
| `modules/key_vault/` | RBAC-only vault. Terraform never sets secret values. |
| `modules/pipeline_job/` | The scheduled Container Apps job and its identity. |
| `modules/dashboard_app/` | The Container App, its identity, and optional Easy Auth. |
| `modules/observability/` | Log Analytics with a daily cap, plus failure and missing-run alerts. |
| `envs/demo`, `envs/prod` | Thin roots that call `stack` with different inputs. |

## Security model

| Identity | Can do | Cannot do |
|---|---|---|
| Pipeline job (per env) | Pull the image; read its Key Vault secrets; write `raw/`, `warehouse/` and `app/` | Read other secrets; touch anything outside its storage account |
| Dashboard (per env) | Pull the image; read `warehouse/`; write `app/` (the saved goal); read the Anthropic key in prod | Read `raw/`; write the warehouse |
| GitHub plan (pull requests) | Read the subscription; lock state | Change any resource |
| GitHub deploy (`demo`/`prod` environments only) | Manage resources, push images, and assign *only* the five workload roles. This is enforced by an ABAC condition on its role assignment. | Grant itself or anyone else Owner, Contributor or any other role |

Other properties of the setup:

- **No keys anywhere.** Storage accounts have shared keys disabled, the registry has its admin user off, and CI logs in through OIDC.
- **No secrets in Terraform state.** Secret values are set once with `az keyvault secret set`, and workloads reference them by URI.
- **Protected data.** `prevent_destroy` is set on the data lake, Key Vault and state storage. Soft delete is on, and Key Vault has purge protection.

### Deliberate trade-offs

These are flagged by checkov, and the skips are documented inline in the Terraform.

| Trade-off | Why | Upgrade path |
|---|---|---|
| No private networking | Private endpoints, a VNet-integrated environment and a Premium registry would cost around €50+/month more for a single-user app. Access is still identity-only. | Add workload profiles with a VNet, private endpoints for storage, Key Vault and ACR, and ACR Premium. |
| Basic container registry | Images are scanned with Trivy in CI before they are pushed. | ACR Premium, for private link, content trust and retention policies. |
| Microsoft-managed encryption keys | Customer-managed keys add a key lifecycle without a threat this data needs. | A customer-managed key in Key Vault, if a policy requires one. |
| ZRS (prod) and LRS (demo) in one region | Keeps data in one EU region. | GZRS to a second EU region, such as North Europe. |

## Cost (approximate, per month)

| Item | Cost |
|---|---|
| Container Registry Basic | about €5 |
| Container Apps (one job run a day, a dashboard that scales to zero) | within the free grant |
| Storage, Key Vault, Log Analytics (capped at 0.5 GB/day) | under €2 |

## First-time setup

You need:
- an Azure subscription where you are Owner
- the `az` CLI and Terraform 1.10 or newer
- the GitHub repository

### 1. Bootstrap (once, locally)

```sh
az login
cd infra/bootstrap
terraform init
terraform apply \
  -var suffix=<3-6 random chars> \
  -var github_repository=<owner>/<repo> \
  -var 'dashboard_user_object_ids=["'"$(az ad signed-in-user show --query id -o tsv)"'"]'
```

Keep `terraform.tfstate` safe. It holds no secrets, but it's the only record of what this layer created.

### 2. GitHub settings

**Environments:**
- `demo`
- `prod`, with yourself as a required reviewer

**Repository variables:**

| Variable | Value |
|---|---|
| `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_CLIENT_ID_PLAN`, `AZURE_CLIENT_ID_DEPLOY`, `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `ACR_LOGIN_SERVER` | The bootstrap outputs with the same names, in lower case (for example `azure_tenant_id`) |
| `REGISTRY_ID` | The `registry_id` output |
| `DASHBOARD_AUTH_CLIENT_ID` | The `dashboard_auth_client_id` output |
| `NAME_SUFFIX` | The `suffix` you chose |
| `DASHBOARD_ALLOWED_OBJECT_IDS`, `SECRET_OFFICER_OBJECT_IDS` | `["<your object id>"]` |

**Repository secret:**
- `ALERT_EMAIL`

### 3. First deploy

1. Run the `deploy` workflow. It builds and pushes the image, then applies `demo`. That works straight away, because the demo needs no secrets.
2. Before approving `prod`, create its Key Vault and set the secrets. The prod Container Apps reference the secrets, so they must exist first.

   ```sh
   cd infra/envs/prod
   terraform init -backend-config=resource_group_name=<tfstate rg> \
     -backend-config=storage_account_name=<tfstate account> -backend-config=key=prod.tfstate
   terraform apply -target=module.stack.module.key_vault   # same TF_VAR_* as in the workflow
   az keyvault secret set --vault-name <kv> --name garmin-tokens --file ../../../.garmin_tokens/garmin_tokens.json
   az keyvault secret set --vault-name <kv> --name anthropic-api-key --value "$ANTHROPIC_API_KEY"
   ```

   Get the Garmin token file by running `uv run ingest garmin` once locally. That's where Garmin may ask for an MFA code.
3. Approve the `prod` deployment in GitHub.
4. Add the prod dashboard URL (the `dashboard_url` output) to bootstrap and apply it again, so Entra ID accepts the sign-in redirect:

   ```sh
   terraform apply ... -var 'dashboard_urls=["https://ca-garminreader-prod-dashboard.<...>.azurecontainerapps.io"]'
   ```

## Running it

- **Every merge to main.** The image is built, scanned and pushed. Then demo is applied, the pipeline runs once and the dashboard is smoke-tested. Prod follows after your approval.
- **Pull requests.** CI runs the tests and the pipeline on synthetic data, and builds and scans the image. Terraform changes also get static checks and a plan comment for each environment.
- **Run the pipeline now:**

  ```sh
  az containerapp job start -n job-garminreader-prod-pipeline -g rg-garminreader-prod
  ```

- **Backfill a range of days.** Run `uv run dagster dev` locally with `RAW_ROOT=abfs://raw`, `DBT_TARGET=azure` and `AZURE_STORAGE_ACCOUNT_NAME` pointing at the prod storage account. Then backfill the `raw/garmin` partitions from the UI. The raw store's change detection makes re-runs safe.
- **Garmin session expiry (about yearly).** Run `uv run ingest garmin` locally, then set `garmin-tokens` again.
