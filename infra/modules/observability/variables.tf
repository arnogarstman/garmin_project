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

variable "alert_email" {
  description = "Where pipeline alerts go."
  type        = string
}

variable "daily_quota_gb" {
  description = "Hard cap on log ingestion per day, against runaway costs."
  type        = number
  default     = 0.5
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}
