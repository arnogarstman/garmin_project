output "name" {
  description = "Name of the job."
  value       = azurerm_container_app_job.this.name
}

output "principal_id" {
  description = "Principal ID of the job's managed identity."
  value       = azurerm_user_assigned_identity.this.principal_id
}
