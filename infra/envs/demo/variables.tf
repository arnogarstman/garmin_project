variable "suffix" {
  description = "Short suffix for globally unique names, as used in bootstrap."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "westeurope"
}

variable "tenant_id" {
  description = "Entra ID tenant ID."
  type        = string
}

variable "image" {
  description = "Image to deploy, tagged with the git commit (set by CI)."
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

variable "alert_email" {
  description = "Where pipeline alerts go (a GitHub secret in CI, so it is not committed)."
  type        = string
  sensitive   = true
}
