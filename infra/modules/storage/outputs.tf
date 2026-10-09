output "account_id" {
  description = "Resource ID of the storage account."
  value       = azurerm_storage_account.this.id
}

output "account_name" {
  description = "Name of the storage account."
  value       = azurerm_storage_account.this.name
}

output "container_ids" {
  description = "Resource IDs of the raw, warehouse and app containers, for container-scoped role assignments."
  value       = { for name, c in azurerm_storage_container.this : name => c.id }
}
