# Provider Docker: a infraestrutura é local, no Docker desta máquina (ou do executor da esteira).
# Windows (Docker Desktop): npipe:////./pipe/docker_engine. Linux e macOS: unix:///var/run/docker.sock.
provider "docker" {
  host = var.docker_host
}
