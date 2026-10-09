# One-off platform layer, applied once by a person with Owner rights (local
# state, see README). It creates what the environments and CI depend on:
#   - remote state storage for the environments
#   - the container registry shared by all environments
#   - the GitHub identities CI logs in with through OIDC (no stored keys)
#   - the Entra ID app registration that protects the prod dashboard

data "azurerm_client_config" "current" {}
data "azurerm_subscription" "current" {}

locals {
  tags = { project = "garminreader", layer = "bootstrap", managed_by = "terraform" }
  # Roles the environment stacks assign to their workload identities. The deploy
  # identity may assign these and nothing else (see the role assignment condition).
  assignable_roles = [
    "Storage Blob Data Contributor",
    "Storage Blob Data Reader",
    "Key Vault Secrets User",
    "Key Vault Secrets Officer", # for the people who set the secret values
    "AcrPull",
  ]
}

resource "azurerm_resource_group" "platform" {
  name     = "rg-${var.project}-platform"
  location = var.location
  tags     = local.tags
}

# -- Terraform state -----------------------------------------------------------

resource "azurerm_storage_account" "tfstate" {
  #checkov:skip=CKV_AZURE_59:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV2_AZURE_33:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV2_AZURE_1:Microsoft-managed encryption keys; customer-managed keys add a key lifecycle without a threat this data needs
  #checkov:skip=CKV_AZURE_206:Data residency in one EU region; ZRS for prod, LRS for the disposable demo
  #checkov:skip=CKV_AZURE_33:Queue service is not used
  name                            = "st${var.project}tfstate${var.suffix}"
  resource_group_name             = azurerm_resource_group.platform.name
  location                        = azurerm_resource_group.platform.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false # Entra ID auth only, for people and CI alike
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  local_user_enabled              = false

  blob_properties {
    versioning_enabled = true # every state version is recoverable
    delete_retention_policy {
      days = 30
    }
    container_delete_retention_policy {
      days = 30
    }
  }

  tags = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "tfstate" {
  #checkov:skip=CKV2_AZURE_21:State access is by CI identities only and versioned; read logging adds cost, not insight
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"

  lifecycle {
    prevent_destroy = true
  }
}

# -- Container registry ----------------------------------------------------------

resource "azurerm_container_registry" "this" {
  #checkov:skip=CKV_AZURE_139:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV_AZURE_163:Images are scanned in CI with Trivy before they are pushed
  #checkov:skip=CKV_AZURE_164:Premium-only registry feature; Basic SKU for cost (about 5 vs 45 euro/month)
  #checkov:skip=CKV_AZURE_165:Single-region deployment
  #checkov:skip=CKV_AZURE_166:Premium-only registry feature; Basic SKU for cost (about 5 vs 45 euro/month)
  #checkov:skip=CKV_AZURE_167:Premium-only registry feature; Basic SKU for cost (about 5 vs 45 euro/month)
  #checkov:skip=CKV_AZURE_233:Premium-only registry feature; Basic SKU for cost (about 5 vs 45 euro/month)
  #checkov:skip=CKV_AZURE_237:Premium-only registry feature; Basic SKU for cost (about 5 vs 45 euro/month)
  name                   = "acr${var.project}${var.suffix}"
  resource_group_name    = azurerm_resource_group.platform.name
  location               = azurerm_resource_group.platform.location
  sku                    = "Basic"
  admin_enabled          = false # pulls use managed identities, pushes use the CI identity
  anonymous_pull_enabled = false
  tags                   = local.tags
}

# -- GitHub Actions identities (OIDC) -------------------------------------------
# plan: read-only, used on pull requests. deploy: applies, used from protected
# GitHub environments only, so a pull request can never deploy.

resource "azurerm_user_assigned_identity" "github_plan" {
  name                = "id-${var.project}-github-plan"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "github_deploy" {
  name                = "id-${var.project}-github-deploy"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "pull_request" {
  name                      = "github-pull-request"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_plan.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:pull_request"
}

resource "azurerm_federated_identity_credential" "environment" {
  for_each                  = toset(var.environments)
  name                      = "github-environment-${each.key}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_deploy.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:environment:${each.key}"
}

# Plan: read everything, and take the state lease (plans lock state).
resource "azurerm_role_assignment" "plan_reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.github_plan.principal_id
}

resource "azurerm_role_assignment" "plan_state" {
  scope                = azurerm_storage_container.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github_plan.principal_id
}

# Deploy: manage resources, write state, push images, and assign only the
# workload roles listed above (an ABAC condition on the RBAC admin role).
resource "azurerm_role_assignment" "deploy_contributor" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
}

data "azurerm_role_definition" "assignable" {
  for_each = toset(local.assignable_roles)
  name     = each.key
  scope    = data.azurerm_subscription.current.id
}

resource "azurerm_role_assignment" "deploy_rbac_admin" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
  condition_version    = "2.0"
  condition            = <<-EOT
    (
      (
        !(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})
      )
      OR
      (
        @Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${join(", ", [for r in data.azurerm_role_definition.assignable : basename(r.role_definition_id)])}}
      )
    )
    AND
    (
      (
        !(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})
      )
      OR
      (
        @Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${join(", ", [for r in data.azurerm_role_definition.assignable : basename(r.role_definition_id)])}}
      )
    )
  EOT
}

resource "azurerm_role_assignment" "deploy_state" {
  scope                = azurerm_storage_container.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
}

resource "azurerm_role_assignment" "deploy_push" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
}

# -- Entra ID app registration for the prod dashboard login ----------------------
# Container Apps' built-in authentication signs users in with this app; only the
# principals listed in the prod environment are let through.

resource "azuread_application" "dashboard" {
  display_name     = "${var.project}-dashboard"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azurerm_client_config.current.object_id]

  web {
    redirect_uris = [for url in var.dashboard_urls : "${trimsuffix(url, "/")}/.auth/login/aad/callback"]
    implicit_grant {
      id_token_issuance_enabled = true # sign-in with ID tokens only: no client secret to manage
    }
  }
}

resource "azuread_service_principal" "dashboard" {
  client_id                    = azuread_application.dashboard.client_id
  app_role_assignment_required = true # only explicitly assigned users can sign in at all
  owners                       = [data.azurerm_client_config.current.object_id]
}

# Assignment is required (above), so each allowed person is assigned explicitly,
# with the default access role.
resource "azuread_app_role_assignment" "dashboard_users" {
  for_each            = toset(var.dashboard_user_object_ids)
  app_role_id         = "00000000-0000-0000-0000-000000000000"
  principal_object_id = each.key
  resource_object_id  = azuread_service_principal.dashboard.object_id
}
