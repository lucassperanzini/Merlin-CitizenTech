output "painel_url" {
  description = "Painel de alertas."
  value       = "http://${var.endereco_publicacao}:${var.portas.painel}"
}

output "prometheus_url" {
  description = "Prometheus."
  value       = "http://${var.endereco_publicacao}:${var.portas.prometheus}"
}

output "grafana_url" {
  description = "Grafana (usuário em grafana_admin_user)."
  value       = "http://${var.endereco_publicacao}:${var.portas.grafana}"
}

output "portas_publicadas" {
  description = "Tudo o que esta pilha publica no computador: só loopback e nenhuma porta de administração."
  value       = [for p in local.portas_publicadas : "${p.servico}: ${p.ip}:${p.externa} -> ${p.interna}"]
}
