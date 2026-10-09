terraform {
  required_version = ">= 1.10"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.9"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.13"
    }
  }

  # Partial configuration: the storage account and resource group come from
  # -backend-config (the bootstrap outputs), so nothing environment-specific
  # beyond the state key is committed. Auth is Entra ID (OIDC in CI).
  backend "azurerm" {
    container_name   = "tfstate"
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {}
  storage_use_azuread = true
}

provider "azapi" {}
