# Infraestrutura local do Merlin CitizenTech: o painel de alertas e a observabilidade (cAdvisor, Prometheus,
# Grafana) numa rede Docker isolada. É a mesma pilha do docker-compose.yml, para ser provisionada e versionada
# como código (e usada pelo deploy da esteira). Rode uma ou outra: as duas usam as mesmas portas.

locals {
  rotulos = {
    "projeto"    = "merlin-citizentech"
    "gerenciado" = "terraform"
  }

  # Todas as portas que esta pilha publica no computador. A política abaixo confere cada uma.
  portas_publicadas = [
    { servico = "painel", interna = 8080, externa = var.portas.painel, ip = var.endereco_publicacao },
    { servico = "prometheus", interna = 9090, externa = var.portas.prometheus, ip = var.endereco_publicacao },
    { servico = "grafana", interna = 3000, externa = var.portas.grafana, ip = var.endereco_publicacao },
  ]
  portas_de_administracao = [22, 23, 2375, 2376, 3389, 5900, 5985, 5986]
  enderecos_abertos       = ["0.0.0.0", "::", ""]

  log_opts = {
    "max-size" = "10m"
    "max-file" = "3"
  }
}

# ---------- Política de portas: o plano falha antes de criar qualquer coisa exposta ----------
resource "terraform_data" "politica_de_portas" {
  input = local.portas_publicadas

  lifecycle {
    precondition {
      condition     = alltrue([for p in local.portas_publicadas : !contains(local.enderecos_abertos, p.ip)])
      error_message = "Nenhuma porta pode ser publicada em 0.0.0.0/0 (ou ::/0): use 127.0.0.1."
    }
    precondition {
      condition = alltrue([for p in local.portas_publicadas :
        !contains(local.portas_de_administracao, p.externa) && !contains(local.portas_de_administracao, p.interna)
      ])
      error_message = "Portas de administração (22, 23, 2375, 2376, 3389, 5900, 5985, 5986) não podem ser publicadas."
    }
  }
}

# ---------- Rede e volumes ----------
resource "docker_network" "monitoramento" {
  name   = "${var.prefixo}-monitoramento"
  driver = "bridge"

  dynamic "labels" {
    for_each = local.rotulos
    content {
      label = labels.key
      value = labels.value
    }
  }
}

resource "docker_volume" "painel_dados" {
  name = "${var.prefixo}-painel-dados"
}

resource "docker_volume" "prometheus_dados" {
  name = "${var.prefixo}-prometheus-dados"
}

resource "docker_volume" "grafana_dados" {
  name = "${var.prefixo}-grafana-dados"
}

# ---------- Imagens ----------
# O painel é construído antes (docker build), e na esteira só depois de passar no Trivy: aqui só é procurado
data "docker_image" "painel" {
  name = var.imagem_painel
}

resource "docker_image" "cadvisor" {
  name         = "ghcr.io/google/cadvisor:v0.53.0"
  keep_locally = true
}

resource "docker_image" "prometheus" {
  name         = "prom/prometheus:v3.5.0"
  keep_locally = true
}

resource "docker_image" "grafana" {
  name         = "grafana/grafana:12.1.1"
  keep_locally = true
}

# ---------- Painel de alertas ----------
resource "docker_container" "painel" {
  name    = "${var.prefixo}-painel"
  image   = data.docker_image.painel.id
  restart = "unless-stopped"

  env = concat(
    [for chave, valor in var.config_robo : "${chave}=${valor}"],
    [
      "FIRMS_MAP_KEY=${var.firms_map_key}",
      "MAPTILER_KEY=${var.maptiler_key}",
      "OUTPUT_CSV=dados/incendio/ocorrencias.csv",
      "PAINEL_PERFIL=${var.painel_perfil}",
      "ALERTAS_INTERVALO=${var.alertas_intervalo}",
      "ALERTAS_BUSCAR_AO_INICIAR=1",
    ],
  )

  ports {
    internal = 8080
    external = var.portas.painel
    ip       = var.endereco_publicacao
  }

  volumes {
    volume_name    = docker_volume.painel_dados.name
    container_path = "/app/dados"
  }

  networks_advanced {
    name    = docker_network.monitoramento.id
    aliases = ["painel"]
  }

  # Endurecimento: sistema de arquivos só leitura, sem capacidades do Linux e sem ganho de privilégios
  read_only     = true
  tmpfs         = { "/tmp" = "size=16m,mode=1777" }
  security_opts = ["no-new-privileges:true"]
  capabilities {
    drop = ["ALL"]
  }
  memory = 512

  log_driver = "json-file"
  log_opts   = local.log_opts

  dynamic "labels" {
    for_each = merge(local.rotulos, { "servico" = "painel" })
    content {
      label = labels.key
      value = labels.value
    }
  }

  depends_on = [terraform_data.politica_de_portas]
}

# ---------- cAdvisor: CPU e memória de cada contêiner (sem porta publicada) ----------
resource "docker_container" "cadvisor" {
  name    = "${var.prefixo}-cadvisor"
  image   = docker_image.cadvisor.image_id
  restart = "unless-stopped"

  # Lê os contêineres pelo containerd (namespace "moby", o do Docker): funciona também no Docker Desktop
  # com o "containerd image store"
  command = [
    "--docker=unix:///run/docker-desligado.sock",
    "--containerd=/run/containerd/containerd.sock",
    "--containerd-namespace=moby",
    "--docker_only=true",
    "--housekeeping_interval=10s",
    "--store_container_labels=false",
    "--disable_metrics=advtcp,cpu_topology,cpuset,hugetlb,memory_numa,percpu,process,referenced_memory,resctrl,sched,tcp,udp",
  ]

  volumes {
    host_path      = "/"
    container_path = "/rootfs"
    read_only      = true
  }
  volumes {
    host_path      = "/var/run"
    container_path = "/var/run"
    read_only      = true
  }
  volumes {
    host_path      = "/sys"
    container_path = "/sys"
    read_only      = true
  }
  volumes {
    host_path      = "/dev/disk"
    container_path = "/dev/disk"
    read_only      = true
  }

  devices {
    host_path = "/dev/kmsg"
  }

  networks_advanced {
    name    = docker_network.monitoramento.id
    aliases = ["cadvisor"]
  }

  security_opts = ["no-new-privileges:true"]
  memory        = 256

  log_driver = "json-file"
  log_opts   = local.log_opts

  dynamic "labels" {
    for_each = merge(local.rotulos, { "servico" = "cadvisor" })
    content {
      label = labels.key
      value = labels.value
    }
  }
}

# ---------- Prometheus ----------
resource "docker_container" "prometheus" {
  name    = "${var.prefixo}-prometheus"
  image   = docker_image.prometheus.image_id
  restart = "unless-stopped"

  command = [
    "--config.file=/etc/prometheus/prometheus.yml",
    "--storage.tsdb.path=/prometheus",
    "--storage.tsdb.retention.time=15d",
  ]

  # A configuração vai junto com o contêiner (funciona igual no Windows e no Linux, sem caminho do computador)
  upload {
    file    = "/etc/prometheus/prometheus.yml"
    content = file("${path.module}/../observability/prometheus/prometheus.yml")
  }

  ports {
    internal = 9090
    external = var.portas.prometheus
    ip       = var.endereco_publicacao
  }

  volumes {
    volume_name    = docker_volume.prometheus_dados.name
    container_path = "/prometheus"
  }

  networks_advanced {
    name    = docker_network.monitoramento.id
    aliases = ["prometheus"]
  }

  security_opts = ["no-new-privileges:true"]
  capabilities {
    drop = ["ALL"]
  }
  memory = 512

  log_driver = "json-file"
  log_opts   = local.log_opts

  dynamic "labels" {
    for_each = merge(local.rotulos, { "servico" = "prometheus" })
    content {
      label = labels.key
      value = labels.value
    }
  }

  depends_on = [terraform_data.politica_de_portas, docker_container.cadvisor, docker_container.painel]
}

# ---------- Grafana ----------
resource "docker_container" "grafana" {
  name    = "${var.prefixo}-grafana"
  image   = docker_image.grafana.image_id
  restart = "unless-stopped"

  env = [
    "GF_SECURITY_ADMIN_USER=${var.grafana_admin_user}",
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
    "GF_USERS_ALLOW_SIGN_UP=false",
    "GF_AUTH_ANONYMOUS_ENABLED=false",
    "GF_SECURITY_DISABLE_GRAVATAR=true",
    "GF_SECURITY_COOKIE_SAMESITE=strict",
    "GF_ANALYTICS_REPORTING_ENABLED=false",
    "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
    "GF_PLUGINS_PLUGIN_ADMIN_ENABLED=false",
  ]

  # Tudo o que está em observability/grafana/provisioning (fontes de dados, e depois painéis e alertas)
  dynamic "upload" {
    for_each = fileset("${path.module}/../observability/grafana/provisioning", "**/*.{yml,yaml,json}")
    content {
      file    = "/etc/grafana/provisioning/${upload.value}"
      content = file("${path.module}/../observability/grafana/provisioning/${upload.value}")
    }
  }

  ports {
    internal = 3000
    external = var.portas.grafana
    ip       = var.endereco_publicacao
  }

  volumes {
    volume_name    = docker_volume.grafana_dados.name
    container_path = "/var/lib/grafana"
  }

  networks_advanced {
    name    = docker_network.monitoramento.id
    aliases = ["grafana"]
  }

  security_opts = ["no-new-privileges:true"]
  capabilities {
    drop = ["ALL"]
  }
  memory = 512

  log_driver = "json-file"
  log_opts   = local.log_opts

  dynamic "labels" {
    for_each = merge(local.rotulos, { "servico" = "grafana" })
    content {
      label = labels.key
      value = labels.value
    }
  }

  depends_on = [terraform_data.politica_de_portas, docker_container.prometheus]
}
