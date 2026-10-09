# Holds the environment's secrets (Garmin session tokens, Anthropic API key).
# Terraform creates the vault and the access, never the secret values: those are
# set once with `az keyvault secret set` (see README), so they are not in state.
# Workloads read them by reference through their managed identity.

resource "azurerm_key_vault" "this" {
  #checkov:skip=CKV_AZURE_189:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV_AZURE_109:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV2_AZURE_32:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 30
  public_network_access_enabled = true # Container Apps on the consumption plan has no private endpoint path

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

# The person running the first apply can set the secret values.
resource "azurerm_role_assignment" "secrets_officer" {
  for_each             = toset(var.secret_officer_principal_ids)
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = each.key
}
