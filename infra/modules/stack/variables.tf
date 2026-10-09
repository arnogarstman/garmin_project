variable "project" {
  description = "Short project name used in resource names."
  type        = string
  default     = "garminreader"
}

variable "environment" {
  description = "Environment name, also the GitHub environment that deploys it."
  type        = string
}

variable "data_profile" {
  description = "prod (real Garmin data) or demo (the simulated athlete)."
  type        = string
  validation {
    condition     = contains(["prod", "demo"], var.data_profile)
    error_message = "data_profile must be prod or demo."
  }
}

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
  description = "Image for both workloads, e.g. acrgarminreaderabc.azurecr.io/garminreader:<git sha>."
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

variable "pipeline_cron" {
  description = "Pipeline schedule in UTC."
  type        = string
  default     = "0 4 * * *"
}

variable "alert_email" {
  description = "Where pipeline alerts go."
  type        = string
}

variable "ai_enabled" {
  description = "Give the dashboard the Anthropic API key (the AI insights cost money per click)."
  type        = bool
  default     = false
}

variable "dashboard_auth" {
  description = "Entra ID sign-in for the dashboard; null for a public one."
  type = object({
    client_id          = string
    tenant_id          = string
    allowed_object_ids = list(string)
  })
  default = null
}

variable "secret_officer_principal_ids" {
  description = "People allowed to set this environment's secret values."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
