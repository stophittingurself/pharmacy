# ============================================================
# Terraform — Infrastructure as Code
#
# Этот файл описывает инфраструктуру в AWS:
#   - VPC (сеть)
#   - EKS (Kubernetes кластер)
#   - ECR (Container Registry — альтернатива Harbor в AWS)
#
# Зачем Terraform когда уже есть Ansible?
#   Terraform = создаёт инфраструктуру (VPC, серверы, кластеры)
#   Ansible   = настраивает серверы (ПО, firewall, конфиги)
#
# Использование:
#   terraform init
#   terraform plan
#   terraform apply
#   terraform destroy
# ============================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "pharmacy-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "pharmacy"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

variable "aws_region" {
  default = "eu-central-1"
}

variable "environment" {
  default = "dev"
}

variable "cluster_name" {
  default = "pharmacy-eks"
}

# ─── VPC ───
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "pharmacy-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ─── EKS Cluster ───
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    general = {
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 5
      desired_size   = 3
      labels = { role = "general" }
    }
  }

  cluster_endpoint_public_access = true
}

# ─── ECR ───
resource "aws_ecr_repository" "backend" {
  name                 = "pharmacy/backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "pharmacy/frontend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# ─── Outputs ───
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "cluster_name"     { value = module.eks.cluster_name }
output "ecr_backend_url"  { value = aws_ecr_repository.backend.repository_url }
output "ecr_frontend_url" { value = aws_ecr_repository.frontend.repository_url }
