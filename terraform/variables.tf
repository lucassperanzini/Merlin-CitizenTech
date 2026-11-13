# ---------- Docker ----------
variable "docker_host" {
  description = "Endereço do Docker. Windows: npipe:////./pipe/docker_engine. Linux/macOS: unix:///var/run/docker.sock."
  type        = string
  default     = "unix:///var/run/docker.sock"
}

variable "prefixo" {
  description = "Prefixo dos nomes de contêineres, volumes e rede (separa esta pilha da do docker compose)."
  type        = string
  default     = "merlin-tf"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.prefixo))
    error_message = "Use só letras minúsculas, números e hífen (2 a 31 caracteres)."
  }
}

variable "imagem_painel" {
  description = "Imagem do painel já construída (docker build -t merlin-painel-alertas:local .). Na esteira, a mesma que passou no Trivy."
  type        = string
  default     = "merlin-painel-alertas:local"
}

# ---------- Rede: nada de porta aberta para a rede ----------
variable "endereco_publicacao" {
  description = "IP do computador em que as portas são publicadas. Só endereços de loopback: nada fica exposto para 0.0.0.0/0."
  type        = string
  default     = "127.0.0.1"

  validation {
    condition     = can(regex("^127\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$", var.endereco_publicacao)) || var.endereco_publicacao == "::1"
    error_message = "Publique só em loopback (127.x.x.x ou ::1). 0.0.0.0, :: ou um IP da rede exporiam os serviços."
  }
}

variable "portas" {
  description = "Portas do computador para o painel, o Prometheus e o Grafana."
  type = object({
    painel     = number
    prometheus = number
    grafana    = number
  })
  default = {
    painel     = 8080
    prometheus = 9090
    grafana    = 3001 # a 3000 costuma estar com o Open WebUI
  }

  validation {
    condition     = alltrue([for porta in values(var.portas) : porta >= 1024 && porta <= 65535])
    error_message = "Use portas de 1024 a 65535 (as abaixo de 1024 são de serviços do sistema)."
  }

  validation {
    condition     = length(setintersection(toset(values(var.portas)), toset([22, 23, 2375, 2376, 3389, 5900, 5985, 5986]))) == 0
    error_message = "Portas de administração (SSH 22, Telnet 23, Docker 2375/2376, RDP 3389, VNC 5900, WinRM 5985/5986) não podem ser publicadas."
  }

  validation {
    condition     = length(distinct(values(var.portas))) == length(values(var.portas))
    error_message = "Cada serviço precisa de uma porta diferente."
  }
}

# ---------- Segredos: só por TF_VAR_* ou terraform.tfvars (fora do Git) ----------
variable "firms_map_key" {
  description = "Chave da API FIRMS da NASA (https://firms.modaps.eosdis.nasa.gov/api/map_key/)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.firms_map_key)) >= 8
    error_message = "Informe a FIRMS_MAP_KEY (TF_VAR_firms_map_key ou terraform.tfvars)."
  }
}

variable "maptiler_key" {
  description = "Chave do MapTiler para os fundos de mapa (opcional; vazia usa o OpenStreetMap)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_admin_user" {
  description = "Usuário administrador do Grafana."
  type        = string
  default     = "admin"
}

variable "grafana_admin_password" {
  description = "Senha do administrador do Grafana (vale na primeira criação do volume de dados)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.grafana_admin_password) >= 12
    error_message = "A senha do Grafana precisa ter pelo menos 12 caracteres."
  }
}

# ---------- Painel e robô FIRMS Monitor (não são segredos) ----------
variable "painel_perfil" {
  description = "operador (só vê) ou administrador (também muda a busca automática)."
  type        = string
  default     = "operador"

  validation {
    condition     = contains(["operador", "administrador"], var.painel_perfil)
    error_message = "Use operador ou administrador."
  }
}

variable "alertas_intervalo" {
  description = "Minutos entre as buscas automáticas (0 desliga)."
  type        = number
  default     = 60

  validation {
    condition     = contains([0, 1, 15, 30, 60, 180, 360, 720, 1440], var.alertas_intervalo)
    error_message = "Use 0, 1, 15, 30, 60, 180, 360, 720 ou 1440."
  }
}

variable "config_robo" {
  description = "Configuração do robô FIRMS Monitor (as mesmas variáveis do .env, sem a chave)."
  type        = map(string)
  default = {
    FIRMS_SOURCE           = "VIIRS_NOAA20_NRT"
    FIRMS_QUERY_MODE       = "area"
    FIRMS_COUNTRY          = "BRA"
    FIRMS_BBOX             = "-74.0,-34.0,-34.7,5.3"
    FIRMS_DAY_RANGE        = "1"
    FIRMS_TIMEOUT_SECONDS  = "60"
    FIRMS_MAX_RETRIES      = "3"
    RISK_MEDIO_FRP         = "10"
    RISK_ALTO_FRP          = "50"
    RISK_CRITICO_FRP       = "100"
    ALERT_MIN_LEVEL        = "ALTO"
    MIN_NUMERIC_CONFIDENCE = "30"
    MIN_FRP                = "0"
    TERRITORY_FILTER       = "BR"
    CSV_DELIMITER          = ","
    LOG_LEVEL              = "INFO"
  }

  validation {
    condition     = !anytrue([for chave in keys(var.config_robo) : contains(["FIRMS_MAP_KEY", "MAPTILER_KEY"], chave)])
    error_message = "As chaves vão nas variáveis firms_map_key e maptiler_key (marcadas como sensíveis), não em config_robo."
  }
}
