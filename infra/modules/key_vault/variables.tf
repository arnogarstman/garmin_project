variable "name" {
  description = "Globally unique Key Vault name (3-24 characters)."
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

variable "tenant_id" {
  description = "Entra ID tenant ID."
  type        = string
}

variable "secret_officer_principal_ids" {
  description = "Principals (people) allowed to set secret values."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}
