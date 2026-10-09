# The Streamlit dashboard as a Container App that scales to zero when nobody
# looks at it. It reads the published warehouse (read-only), keeps the saved
# goal in the app container, and optionally sits behind Entra ID sign-in.

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

resource "azurerm_role_assignment" "read_warehouse" {
  scope                = var.warehouse_container_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_role_assignment" "write_app_state" {
  scope                = var.app_container_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_role_assignment" "secrets" {
  for_each             = var.secrets
  scope                = "${var.key_vault_id}/secrets/${each.value}"
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

resource "azurerm_container_app" "this" {
  name                         = var.name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.environment_id
  revision_mode                = "Single"

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

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "auto" # Streamlit needs websockets
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1 # one replica: the app keeps a local copy of the warehouse

    container {
      name   = "dashboard"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

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

      startup_probe {
        transport               = "HTTP"
        port                    = 8501
        path                    = "/_stcore/health"
        failure_count_threshold = 10
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8501
        path      = "/_stcore/health"
      }
    }
  }

  tags = var.tags

  depends_on = [azurerm_role_assignment.pull, azurerm_role_assignment.secrets]
}

# Built-in authentication (Easy Auth): unauthenticated requests are redirected
# to Entra ID sign-in, and only the listed principals get through. azurerm has
# no resource for Container Apps auth, hence azapi.
resource "azapi_resource" "auth" {
  count     = var.auth == null ? 0 : 1
  type      = "Microsoft.App/containerApps/authConfigs@2024-03-01"
  name      = "current"
  parent_id = azurerm_container_app.this.id

  body = {
    properties = {
      platform = { enabled = true }
      globalValidation = {
        unauthenticatedClientAction = "RedirectToLoginPage"
        redirectToProvider          = "azureactivedirectory"
      }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId     = var.auth.client_id
            openIdIssuer = "https://login.microsoftonline.com/${var.auth.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [var.auth.client_id]
            defaultAuthorizationPolicy = {
              allowedPrincipals = { identities = var.auth.allowed_object_ids }
            }
          }
        }
      }
    }
  }
}
