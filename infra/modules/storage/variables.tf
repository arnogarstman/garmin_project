variable "name" {
  description = "Globally unique storage account name (3-24 lowercase letters and digits)."
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

variable "replication_type" {
  description = "LRS is enough for demo data; ZRS keeps prod data across zones."
  type        = string
  default     = "ZRS"
}

variable "soft_delete_days" {
  description = "Days deleted blobs and containers stay recoverable."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}

variable "log_analytics_workspace_id" {
  description = "Workspace that receives the blob access logs."
  type        = string
}
