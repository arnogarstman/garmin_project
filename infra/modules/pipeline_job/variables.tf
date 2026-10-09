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

variable "cron_expression" {
  description = "When to run, in UTC (Container Apps schedules are UTC)."
  type        = string
  default     = "0 4 * * *"
}

variable "timeout_seconds" {
  description = "Maximum run time of one execution."
  type        = number
  default     = 1800
}

variable "cpu" {
  description = "vCPU per execution."
  type        = number
  default     = 1
}

variable "memory" {
  description = "Memory per execution."
  type        = string
  default     = "2Gi"
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

variable "writable_container_ids" {
  description = "Storage containers the job may write, by name."
  type        = map(string)
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}
