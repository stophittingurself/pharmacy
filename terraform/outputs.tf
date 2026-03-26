output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "rds_endpoint" {
  value = aws_db_instance.pharmacy.endpoint
}

output "rds_database_url" {
  value     = "postgresql://pharmacy:${var.db_password}@${aws_db_instance.pharmacy.endpoint}/pharmacy_db"
  sensitive = true
}

output "vpc_id" {
  value = aws_vpc.main.id
}

# Команда для подключения kubectl к кластеру
output "kubectl_config_command" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}
