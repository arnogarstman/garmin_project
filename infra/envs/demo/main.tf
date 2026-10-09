# Public demo: the simulated athlete, a public dashboard without the paid AI features.
module "stack" {
  source          = "../../modules/stack"
  environment     = "demo"
  data_profile    = "demo"
  suffix          = var.suffix
  location        = var.location
  tenant_id       = var.tenant_id
  image           = var.image
  registry_server = var.registry_server
  registry_id     = var.registry_id
  alert_email     = var.alert_email
  ai_enabled      = false
}
