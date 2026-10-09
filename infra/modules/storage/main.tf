# The data lake for one environment: raw (bronze, append-only NDJSON), the
# published warehouse file, and small app state (the saved training goal).
# Entra ID access only: no account keys, no SAS, nothing public.

resource "azurerm_storage_account" "this" {
  #checkov:skip=CKV_AZURE_59:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV2_AZURE_33:Network isolation traded for cost (private endpoints, VNet-integrated Container Apps); access is Entra ID only, no keys. See infra/README.md
  #checkov:skip=CKV2_AZURE_1:Microsoft-managed encryption keys; customer-managed keys add a key lifecycle without a threat this data needs
  #checkov:skip=CKV_AZURE_206:Data residency in one EU region; ZRS for prod, LRS for the disposable demo
  #checkov:skip=CKV_AZURE_33:Queue service is not used
  name                            = var.name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = var.replication_type
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true # ADLS Gen2: real directories for the endpoint=/load_date= partitions
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  local_user_enabled              = false # no SFTP/local users: identities only

  blob_properties {
    delete_retention_policy {
      days = var.soft_delete_days
    }
    container_delete_retention_policy {
      days = var.soft_delete_days
    }
  }

  tags = var.tags

  lifecycle {
    prevent_destroy = true # the raw layer is the only full copy of the history
  }
}

resource "azurerm_storage_container" "this" {
  #checkov:skip=CKV2_AZURE_21:Blob access is logged through the account diagnostic setting below
  for_each              = toset(["raw", "warehouse", "app"])
  name                  = each.key
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"

  lifecycle {
    prevent_destroy = true
  }
}

# Raw files are written once and rarely read after the first dbt build: move them
# to the cool tier after a month. They stay readable, so a full rebuild still works.
resource "azurerm_storage_management_policy" "this" {
  storage_account_id = azurerm_storage_account.this.id

  rule {
    name    = "raw-to-cool"
    enabled = true
    filters {
      prefix_match = ["raw/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
      }
    }
  }
}

# Audit trail: every read, write and delete on the data lake goes to the
# environment's Log Analytics workspace.
resource "azurerm_monitor_diagnostic_setting" "blob" {
  name                       = "blob-access-logs"
  target_resource_id         = "${azurerm_storage_account.this.id}/blobServices/default"
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "StorageRead"
  }
  enabled_log {
    category = "StorageWrite"
  }
  enabled_log {
    category = "StorageDelete"
  }
}
