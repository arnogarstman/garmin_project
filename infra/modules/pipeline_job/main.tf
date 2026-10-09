# The daily pipeline (`pipeline`: ingest, dbt build and checks, publish) as a
# scheduled Container Apps job with its own identity. It can pull the image,
# read only the secrets it is given, and write only the containers it needs.

resource "azurerm_user_assigned_identity" "this" {
  name                = "id-${var.name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "pull" {
  scope                = var.registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_role_assignment" "write" {
  for_each             = var.writable_container_ids
  scope                = each.value
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_role_assignment" "secrets" {
  for_each             = var.secrets
  scope                = "${var.key_vault_id}/secrets/${each.value}"
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_container_app_job" "this" {
  name                         = var.name
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.environment_id
  replica_timeout_in_seconds   = var.timeout_seconds
  replica_retry_limit          = 1 # Dagster already retries the Garmin step; this covers a crashed container

  schedule_trigger_config {
    cron_expression          = var.cron_expression
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  registry {
    server   = var.registry_server
    identity = azurerm_user_assigned_identity.this.id
  }

  dynamic "secret" {
    for_each = var.secrets
    content {
      name                = secret.value
      identity            = azurerm_user_assigned_identity.this.id
      key_vault_secret_id = "${var.key_vault_uri}secrets/${secret.value}"
    }
  }

  template {
    container {
      name    = "pipeline"
      image   = var.image
      command = ["pipeline"]
      cpu     = var.cpu
      memory  = var.memory

      dynamic "env" {
        for_each = merge(var.env, { AZURE_CLIENT_ID = azurerm_user_assigned_identity.this.client_id })
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secrets
        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }

  tags = var.tags

  # The identity must be able to pull the image and read its secrets before the
  # first execution, so the role assignments come first.
  depends_on = [azurerm_role_assignment.pull, azurerm_role_assignment.secrets]
}
