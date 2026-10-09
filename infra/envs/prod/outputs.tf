output "dashboard_url" {
  description = "Public URL of the dashboard."
  value       = module.stack.dashboard_url
}

output "pipeline_job_name" {
  description = "Name of the scheduled pipeline job (start it by hand with az containerapp job start)."
  value       = module.stack.pipeline_job_name
}

output "resource_group_name" {
  description = "Resource group of the environment."
  value       = module.stack.resource_group_name
}

output "key_vault_uri" {
  description = "Key Vault to set the secret values in."
  value       = module.stack.key_vault_uri
}
