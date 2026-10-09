variable "project" {
  description = "Short project name used in resource names."
  type        = string
  default     = "garminreader"
}

variable "suffix" {
  description = "Short random suffix for globally unique names (storage account, registry)."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9]{3,6}$", var.suffix))
    error_message = "Use 3-6 lowercase letters or digits."
  }
}

variable "location" {
  description = "Azure region. West Europe is in the Netherlands, within the EU Data Boundary."
  type        = string
  default     = "westeurope"
}

variable "github_repository" {
  description = "GitHub repository CI runs in, as owner/name."
  type        = string
}

variable "environments" {
  description = "GitHub environments allowed to deploy (each needs a matching infra/envs/<name>)."
  type        = list(string)
  default     = ["demo", "prod"]
}

variable "dashboard_urls" {
  description = "Public URLs of the prod dashboard, for the login redirect. Empty on the first apply; add the URL from the prod outputs and apply again."
  type        = list(string)
  default     = []
}

variable "dashboard_user_object_ids" {
  description = "Object IDs of the people allowed to sign in to the prod dashboard (az ad signed-in-user show --query id)."
  type        = list(string)
}
