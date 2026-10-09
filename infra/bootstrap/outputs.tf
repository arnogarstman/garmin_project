# Set the upper-cased names as GitHub repository variables (not secrets: none of
# them is a credential), e.g. azure_tenant_id -> AZURE_TENANT_ID.

output "azure_tenant_id" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = data.azurerm_client_config.current.tenant_id
}

output "azure_subscription_id" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = data.azurerm_client_config.current.subscription_id
}

output "azure_client_id_plan" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = azurerm_user_assigned_identity.github_plan.client_id
}

output "azure_client_id_deploy" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = azurerm_user_assigned_identity.github_deploy.client_id
}

output "tfstate_resource_group" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = azurerm_resource_group.platform.name
}

output "tfstate_storage_account" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = azurerm_storage_account.tfstate.name
}

output "acr_login_server" {
  description = "Value for the GitHub repository variable of the same name, in upper case."
  value       = azurerm_container_registry.this.login_server
}

output "registry_id" {
  description = "Resource ID of the container registry, an input of the environments."
  value       = azurerm_container_registry.this.id
}

output "dashboard_auth_client_id" {
  description = "Client ID of the dashboard app registration, an input of the prod environment."
  value       = azuread_application.dashboard.client_id
}
