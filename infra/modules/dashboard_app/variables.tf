variable "name" {
  description = "Resource name."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group to create the resources in."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "environment_id" {
  description = "Container Apps environment to run in."
  type        = string
}

variable "image" {
  description = "Fully qualified image reference, tagged with the git commit."
  type        = string
}

variable "registry_server" {
  description = "Login server of the container registry, e.g. acrgarminreaderabc.azurecr.io."
  type        = string
}

variable "registry_id" {
  description = "Resource ID of the container registry (for the AcrPull role assignment)."
  type        = string
}

variable "env" {
  description = "Plain environment variables."
  type        = map(string)
}

variable "secrets" {
  description = "Environment variable name => Key Vault secret name, read by reference."
  type        = map(string)
  default     = {}
}

variable "key_vault_id" {
  description = "Resource ID of the Key Vault holding the secrets."
  type        = string
}

variable "key_vault_uri" {
  description = "URI of the Key Vault holding the secrets."
  type        = string
}

variable "warehouse_container_id" {
  description = "Resource ID of the storage container with the published warehouse."
  type        = string
}

variable "app_container_id" {
  description = "Resource ID of the storage container with app state (the saved goal)."
  type        = string
}

variable "auth" {
  description = "Entra ID sign-in. Null makes the dashboard public (the demo)."
  type = object({
    client_id          = string
    tenant_id          = string
    allowed_object_ids = list(string)
  })
  default = null
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}
