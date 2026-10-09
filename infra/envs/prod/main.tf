# Private: your own Garmin data, behind Entra ID sign-in, with the AI features on.
module "stack" {
  source                       = "../../modules/stack"
  environment                  = "prod"
  data_profile                 = "prod"
  suffix                       = var.suffix
  location                     = var.location
  tenant_id                    = var.tenant_id
  image                        = var.image
  registry_server              = var.registry_server
  registry_id                  = var.registry_id
  alert_email                  = var.alert_email
  ai_enabled                   = true
  secret_officer_principal_ids = var.secret_officer_principal_ids
  dashboard_auth = {
    client_id          = var.dashboard_auth_client_id
    tenant_id          = var.tenant_id
    allowed_object_ids = var.dashboard_allowed_object_ids
  }
}
