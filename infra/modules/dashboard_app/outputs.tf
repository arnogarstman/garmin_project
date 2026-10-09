output "url" {
  description = "Public URL of the dashboard."
  value       = "https://${azurerm_container_app.this.ingress[0].fqdn}"
}
