# ReTOSCA

**Infrastructure Intent Discovery via TOSCA-based Reverse Engineering**

A proof-of-concept tool that **discovers and reconstructs the original architectural intent** from Infrastructure as Code (IaC) configurations. ReTOSCA reverse-engineers IaC files to understand topology relationships, dependencies, and design patterns, then represents this discovered intent as semantically consistent TOSCA 2.0 models.

## 🏗️ Architecture

ReTOSCA uses a **plugin-based architecture** with a multi-phase pipeline approach:

### Core Components
- **Protocol-Based Design**: `src/core/protocols.py` defines contracts (`SourceFileParser`, `SingleResourceMapper`, `ResourceMapper`, `PhasePlugin`)
- **Pipeline Runner**: Orchestrates execution of multiple phase plugins in sequence
- **Plugin Registry**: Manages available plugins with dynamic discovery and instantiation
- **TOSCA Model Generation**: Pydantic-based models for TOSCA 2.0 with fluent builders

### Plugin System
- **Multi-Phase Pipeline**: Plugins are **chainable** - you can create additional phases and link them with any plugin technology
- **Current Implementation**: Terraform AWS provisioning phase (30+ resource mappers)
- **Extensible Design**: Architecture supports adding new phases (configuration management, orchestration, security analysis) that can work with any IaC technology
- **Phase Composition**: Each phase enriches the shared TOSCA model, enabling complex multi-technology scenarios

### Technology Stack
- **Python 3.11+** with Poetry dependency management
- **Pydantic Models** for TOSCA 2.0 schema validation and type safety
- **Protocol-Based Architecture** for plugin extensibility
- **YAML Generation** with ruamel.yaml for TOSCA output
- **Docker Support** for containerized execution
- **Plugin-Specific Parsers** loaded dynamically per technology

## 🚀 Usage

### Quick Start with Examples

```bash
# Download specific example configurations to test

# Simple S3 bucket example
mkdir -p examples/basic/aws_s3_bucket
curl -L https://raw.githubusercontent.com/your-repo/ReTOSCA/master/examples/basic/aws_s3_bucket/main.tf -o examples/basic/aws_s3_bucket/main.tf

# EC2 instance example
mkdir -p examples/basic/aws_instance
curl -L https://raw.githubusercontent.com/your-repo/ReTOSCA/master/examples/basic/aws_instance/main.tf -o examples/basic/aws_instance/main.tf

# Complex MVC example
mkdir -p examples/mvc
curl -L https://raw.githubusercontent.com/your-repo/ReTOSCA/master/examples/mvc/main.tf -o examples/mvc/main.tf

# Or clone the full repository for all examples
git clone https://github.com/your-repo/ReTOSCA.git
cd ReTOSCA
```

### Docker (Recommended)

```bash
# Download docker-compose.yaml
curl -O https://raw.githubusercontent.com/your-repo/ReTOSCA/master/docker-compose.yaml

# Run with downloaded examples
INPUT_DIR="$PWD/examples/basic/aws_s3_bucket" OUTPUT_DIR="$PWD/output" docker compose run --rm retosca python -m src.main --source "terraform:/work/input" /work/output/model.yaml

# Run with your own Terraform files
INPUT_DIR="/path/to/your/terraform" OUTPUT_DIR="/path/to/output" docker compose run --rm retosca python -m src.main --source "terraform:/work/input" /work/output/model.yaml
```

### Local Development

```bash
# Clone and install
git clone <repository-url>
cd ReTOSCA
poetry install

# Run with included examples
poetry run python -m src.main --source terraform:examples/basic/aws_s3_bucket output/s3_model.yaml
poetry run python -m src.main --source terraform:examples/mvc output/mvc_model.yaml

# Run with your own Terraform
poetry run python -m src.main --source terraform:/path/to/terraform/directory output/model.yaml
```

### Getting Help

```bash
# List available plugins and options
poetry run python -m src.main --help

# List available plugin types
poetry run python -m src.main --list-plugins
```

## 🎯 Current Implementation

### Terraform AWS → TOSCA (Provisioning Phase)

| Category | Resources | Count |
|----------|-----------|-------|
| **Compute** | EC2 instances, EBS volumes, volume attachments | 3 |
| **Networking** | VPC, subnets, security groups, internet gateways, NAT gateways, routes, route tables | 9 |
| **Storage** | S3 buckets | 1 |
| **Database** | RDS instances, RDS clusters, DB subnet groups | 3 |
| **Caching** | ElastiCache clusters, replication groups, subnet groups | 3 |
| **Load Balancing** | Application/Network load balancers, target groups, listeners, attachments | 4 |
| **DNS** | Route53 hosted zones and records | 2 |
| **Security** | IAM roles, policies, security group rules | 5 |
| **Network Associations** | Route table associations, VPC CIDR associations | 2 |
| **Elastic IPs** | Elastic IP addresses | 1 |
| **Total** | **AWS Resources Supported** | **33** |

### Future Phases (Architecture Ready)
- **Configuration Management**: Ansible, Chef, Puppet → TOSCA policies and workflows
- **Container Orchestration**: Kubernetes, Docker Compose → TOSCA container nodes
- **Security Analysis**: Security scanning tools → TOSCA security policies
- **Multi-Cloud**: Azure ARM, GCP Deployment Manager → unified TOSCA model

## 📁 Examples

The `examples/` directory contains Terraform configurations organized by complexity:

### Basic Examples (Single Resources)
- `aws_s3_bucket/`: Simple S3 bucket with tags
- `aws_instance/`: EC2 instance with security group
- `aws_vpc/`: VPC with CIDR block configuration
- `aws_db_instance/`: RDS database instance
- `aws_elasticache_cluster/`: ElastiCache cluster setup

### Composed Examples (Multi-Resource)
- `aws_compute_storage/`: EC2 instance with EBS volume attachment
- `aws_lb/`: Load balancer with target groups and listeners
- `aws_route_table/`: VPC with custom routing configuration
- `aws_storage_subnet_sg/`: Multi-tier networking with storage

### Advanced Examples (Complex Scenarios)
- `mvc/`: **Complete 3-tier web application** (presentation, business, data layers)
- `count/`: Resource replication using Terraform count
- `loops/`: Dynamic resource creation with for_each
- `route53_zones/`: DNS management with multiple zones

### Model-View-Controller (MVC) Example
The `mvc/` example demonstrates a complete web application topology:
- **Presentation Layer**: Load balancer, public subnets, security groups
- **Business Layer**: Application servers, private subnets, auto-scaling
- **Data Layer**: RDS cluster, ElastiCache, database subnets
- **Cross-cutting**: VPC, internet gateway, NAT gateways, Route53

## 🔧 Intent Discovery & Output

ReTOSCA **discovers and reconstructs** the original infrastructure intent by:

### Topology Understanding
- **Relationship Discovery**: Identifies dependencies between resources (VPC → Subnet → Instance)
- **Architectural Pattern Recognition**: Detects common patterns (3-tier architecture, load balancing, database clustering)
- **Resource Grouping**: Understands logical groupings and their purposes
- **Network Topology Mapping**: Reconstructs network flow and security boundaries

### TOSCA 2.0 Representation
Generates **semantically rich TOSCA models** that capture the discovered intent:
- **Node Templates**: Infrastructure components with their intended purpose
- **Relationship Mappings**: Explicit dependencies and connections
- **Capability Modeling**: What each component provides to others
- **Requirement Modeling**: What each component needs from others
- **Properties & Attributes**: Configuration that reflects design decisions
- **Validation**: Ensures the discovered topology is structurally sound

## 🔍 Development Workflow

1. **Add Resource Support**: Create mapper classes in `src/plugins/terraform/mappers/aws/`
2. **Register Mappers**: Add to `TerraformProvisioningPlugin._register_mappers()`
3. **Extend Phases**: Create plugins inheriting from `BasePhasePlugin`
4. **Test**: Use `pytest` with markers (`unit`, `integration`, `slow`)
5. **Validate**: LocalStack integration for real AWS API testing

## ⚠️ Status

**This is a proof of concept for infrastructure intent discovery.** Use for:
- **Topology Analysis**: Understanding complex infrastructure relationships and dependencies
- **Architectural Documentation**: Generating visual and semantic representations of infrastructure intent
- **Migration Planning**: Discovering current architecture before cross-platform migration
- **Legacy Infrastructure Understanding**: Reverse-engineering existing IaC to understand original design
- **Compliance & Governance**: Analyzing whether deployed infrastructure matches intended architecture
- **Research**: Experimenting with infrastructure intent modeling and TOSCA representation

Not recommended for production infrastructure management.
