output "id" {
  description = "Resource ID."
  value       = azurerm_key_vault.this.id
}

output "uri" {
  description = "Vault URI, for secret references."
  value       = azurerm_key_vault.this.vault_uri
}
