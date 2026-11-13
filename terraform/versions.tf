# Versões do Terraform e do provider. O .terraform.lock.hcl (gerado pelo terraform init) vai para o Git:
# ele fixa a versão exata e o hash do provider, para todo mundo e a esteira usarem o mesmo binário.
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.6"
    }
  }
}
