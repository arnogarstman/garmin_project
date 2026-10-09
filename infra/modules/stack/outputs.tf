output "dashboard_url" {
  description = "Public URL of the dashboard."
  value       = module.dashboard.url
}

output "pipeline_job_name" {
  description = "Name of the scheduled pipeline job (start it by hand with az containerapp job start)."
  value       = module.pipeline.name
}

output "resource_group_name" {
  description = "Resource group of the environment."
  value       = azurerm_resource_group.this.name
}

output "key_vault_uri" {
  description = "Key Vault to set the secret values in."
  value       = module.key_vault.uri
}

output "storage_account_name" {
  description = "Data lake storage account."
  value       = module.storage.account_name
}
