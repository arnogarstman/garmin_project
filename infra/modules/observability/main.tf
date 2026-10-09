# Logs for the environment's containers, with a hard daily ingestion cap so a
# noisy bug cannot run up a bill, plus alerts on the pipeline's own signals.

resource "azurerm_log_analytics_workspace" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = var.daily_quota_gb
  tags                = var.tags
}

resource "azurerm_monitor_action_group" "email" {
  name                = "ag-${var.name}"
  resource_group_name = var.resource_group_name
  short_name          = "pipeline"

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }

  tags = var.tags
}

locals {
  # Container Apps writes console logs to either table, depending on the
  # environment's log configuration; query both.
  console_logs = "union isfuzzy=true ContainerAppConsoleLogs, ContainerAppConsoleLogs_CL | extend line = coalesce(column_ifexists('Log', ''), column_ifexists('Log_s', ''))"
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "pipeline_failed" {
  name                 = "alert-${var.name}-pipeline-failed"
  resource_group_name  = var.resource_group_name
  location             = var.location
  description          = "The daily pipeline run failed (a Dagster step or an error-level check)."
  severity             = 1
  scopes               = [azurerm_log_analytics_workspace.this.id]
  evaluation_frequency = "PT1H"
  window_duration      = "PT1H"

  criteria {
    query                   = "${local.console_logs} | where line has 'RUN_FAILURE' or line has 'Failed checks'"
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0
  }

  action {
    action_groups = [azurerm_monitor_action_group.email.id]
  }

  tags = var.tags
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "pipeline_missing" {
  name                 = "alert-${var.name}-pipeline-missing"
  resource_group_name  = var.resource_group_name
  location             = var.location
  description          = "No successful pipeline run for over a day: the schedule or the job is broken."
  severity             = 2
  scopes               = [azurerm_log_analytics_workspace.this.id]
  evaluation_frequency = "PT6H"
  window_duration      = "P1D"

  criteria {
    query                   = "${local.console_logs} | where line has 'RUN_SUCCESS'"
    time_aggregation_method = "Count"
    operator                = "LessThan"
    threshold               = 1
  }

  action {
    action_groups = [azurerm_monitor_action_group.email.id]
  }

  tags = var.tags
}
