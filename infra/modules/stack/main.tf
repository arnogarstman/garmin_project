# One complete environment of the app: logs and alerts, the data lake, secrets,
# the Container Apps environment, the scheduled pipeline and the dashboard.
# envs/demo and envs/prod are thin wrappers around this module, so both
# environments are built the same way and differ only in their inputs.

locals {
  name      = "${var.project}-${var.environment}"
  is_demo   = var.data_profile == "demo"
  prefix    = local.is_demo ? "DEMO_" : "" # settings the app reads for the active profile (see config.py)
  compact   = replace(var.project, "-", "")
  tags      = merge(var.tags, { project = var.project, environment = var.environment, managed_by = "terraform" })
  warehouse = "abfs://warehouse/warehouse.duckdb"

  # Settings shared by both workloads: where the data lives, and how to reach it
  # (adlfs and dbt authenticate with the workload's managed identity).
  common_env = {
    DATA_PROFILE                   = var.data_profile
    AZURE_STORAGE_ACCOUNT_NAME     = module.storage.account_name
    "${local.prefix}WAREHOUSE_URL" = local.warehouse
    "${local.prefix}GOAL_PATH"     = "abfs://app/goal.json"
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

module "observability" {
  source              = "../observability"
  name                = "log-${local.name}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  alert_email         = var.alert_email
  tags                = local.tags
}

module "storage" {
  source              = "../storage"
  name                = "st${local.compact}${var.environment}${var.suffix}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  replication_type    = local.is_demo ? "LRS" : "ZRS"

  log_analytics_workspace_id = module.observability.workspace_id
  tags                       = local.tags
}

module "key_vault" {
  source                       = "../key_vault"
  name                         = "kv-${local.compact}-${var.environment}-${var.suffix}"
  resource_group_name          = azurerm_resource_group.this.name
  location                     = var.location
  tenant_id                    = var.tenant_id
  secret_officer_principal_ids = var.secret_officer_principal_ids
  tags                         = local.tags
}

resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${local.name}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  log_analytics_workspace_id = module.observability.workspace_id
  logs_destination           = "log-analytics"
  tags                       = local.tags
}

module "pipeline" {
  source              = "../pipeline_job"
  name                = "job-${local.name}-pipeline"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  environment_id      = azurerm_container_app_environment.this.id
  image               = var.image
  registry_server     = var.registry_server
  registry_id         = var.registry_id
  cron_expression     = var.pipeline_cron
  key_vault_id        = module.key_vault.id
  key_vault_uri       = module.key_vault.uri
  # The demo simulates its data; only real data needs a Garmin session.
  secrets = local.is_demo ? {} : { GARMINTOKENS = "garmin-tokens" }
  env = merge(local.common_env, {
    DBT_TARGET                = "azure"
    "${local.prefix}RAW_ROOT" = "abfs://raw"
  })
  writable_container_ids = {
    raw       = module.storage.container_ids["raw"]
    warehouse = module.storage.container_ids["warehouse"]
    app       = module.storage.container_ids["app"] # the demo writes its preset goal
  }
  tags = local.tags
}

module "dashboard" {
  source                 = "../dashboard_app"
  name                   = "ca-${local.name}-dashboard"
  resource_group_name    = azurerm_resource_group.this.name
  location               = var.location
  environment_id         = azurerm_container_app_environment.this.id
  image                  = var.image
  registry_server        = var.registry_server
  registry_id            = var.registry_id
  key_vault_id           = module.key_vault.id
  key_vault_uri          = module.key_vault.uri
  warehouse_container_id = module.storage.container_ids["warehouse"]
  app_container_id       = module.storage.container_ids["app"]
  # AI features call a paid API: only where the audience is trusted.
  secrets = var.ai_enabled ? { ANTHROPIC_API_KEY = "anthropic-api-key" } : {}
  env     = local.common_env
  auth    = var.dashboard_auth
  tags    = local.tags
}
