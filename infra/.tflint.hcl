# Run per root with: tflint --init && tflint --recursive --config "$(pwd)/.tflint.hcl"
config {
  call_module_type = "local" # also lint the modules, with the values the roots pass in
}

plugin "terraform" {
  enabled = true
  preset  = "all"
}

plugin "azurerm" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}
