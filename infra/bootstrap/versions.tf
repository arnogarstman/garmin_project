terraform {
  required_version = ">= 1.10"
  # Local state on purpose: this layer creates the remote state storage itself.
  # Keep terraform.tfstate safe (it holds no secrets), or import on re-creation.
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.9"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.10"
    }
  }
}

provider "azurerm" {
  features {}
  storage_use_azuread = true
}

provider "azuread" {}
