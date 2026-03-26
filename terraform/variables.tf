variable "aws_region" {
  description = "AWS регион"
  default     = "eu-central-1"  # Франкфурт — ближайший к Казахстану
}

variable "environment" {
  description = "Окружение (dev/stage/prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR блок VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Зоны доступности"
  default     = ["eu-central-1a", "eu-central-1b"]
}

variable "k8s_version" {
  description = "Версия Kubernetes для EKS"
  default     = "1.30"
}

variable "node_instance_type" {
  description = "Тип EC2 инстансов для K8s нод"
  default     = "t3.medium"
}

variable "node_desired" {
  description = "Желаемое количество нод"
  default     = 2
}

variable "node_min" {
  description = "Минимум нод"
  default     = 1
}

variable "node_max" {
  description = "Максимум нод"
  default     = 5
}

variable "db_instance_class" {
  description = "Класс RDS инстанса"
  default     = "db.t3.micro"
}

variable "db_storage" {
  description = "Размер диска RDS (GB)"
  default     = 20
}

variable "db_password" {
  description = "Пароль PostgreSQL"
  type        = string
  sensitive   = true
}
