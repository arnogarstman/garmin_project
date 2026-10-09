terraform {
  required_version = ">= 1.10"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 5.9"
    }
    azapi = {
      source  = "Azure/azapi"
      version = ">= 2.13"
    }
  }
}
