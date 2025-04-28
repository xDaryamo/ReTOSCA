"""
Category-to-Node heuristic.

* No side-effects, no exceptions – return `NodeCategory` or ``None``.
* Priority
  1. Type rules      → simple case-insensitive *substring* search
  2. Capability rules → scan capability names / types
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.ir.models import NodeCategory

from .capability_rule import CapabilityRule
from .type_rule import TypeRule

__all__ = ["infer_category"]

logger = logging.getLogger(__name__)

TYPE_RULES: list[TypeRule] = [
    # Compute
    TypeRule(
        patterns=[
            "compute",
            "server",
            "instance",
            "vm",
            "vps",
            "node",
            "worker",
            "virtualmachine",
            "baremetal",
            "hypervisor",
            "droplet",
            "ec2",
            "gce",
            "azurevm",
            "ecs",
            "eksnode",
            "aksnode",
            "ocean",
            "lxd",
            "kvm",
            "xen",
            "qemu",
            "hyperv",
            "fargate",
            "containerinstance",
            "edgecompute",
            "fognode",
            "tosca.nodes.Compute",
        ],
        category=NodeCategory.COMPUTE,
    ),
    # Storage
    TypeRule(
        patterns=[
            "storage",
            "volume",
            "disk",
            "drive",
            "lun",
            "snapshot",
            "bucket",
            "blob",
            "objectstore",
            "objectstorage",
            "fileshare",
            "filestore",
            "mount",
            "ebs",
            "pdssd",
            "pdstandard",
            "gp2",
            "gp3",
            "efs",
            "fsx",
            "s3",
            "gcs",
            "swift",
            "oss",
            "tosca.nodes.BlockStorage",
            "tosca.nodes.ObjectStorage",
        ],
        category=NodeCategory.STORAGE,
    ),
    # Network
    TypeRule(
        patterns=[
            "network",
            "vpc",
            "vnet",
            "subnet",
            "segment",
            "vxlan",
            "vlan",
            "router",
            "gateway",
            "nat",
            "vpn",
            "peering",
            "transitgateway",
            "lb",
            "loadbalancer",
            "elb",
            "alb",
            "nlb",
            "firewall",
            "securitygroup",
            "nsg",
            "acl",
            "dns",
            "domain",
            "ingress",
            "egress",
            "interface",
            "eni",
            "nic",
            "route",
            "link",
            "bridge",
            "bond",
            "istio",
            "linkerd",
            "serviceentry",
            "tosca.nodes.network.Network",
            "virtuallink",
        ],
        category=NodeCategory.NETWORK,
    ),
    # Software / Application
    TypeRule(
        patterns=[
            "software",
            "service",
            "application",
            "app",
            "microservice",
            "webserver",
            "webapp",
            "site",
            "portal",
            "apigateway",
            "reverseproxy",
            "proxy",
            "daemon",
            "worker",
            "job",
            "cronjob",
            "task",
            "client",
            "agent",
            "frontend",
            "backend",
            "middleware",
            "k8sdeployment",
            "statefulset",
            "replicaset",
            "pod",
            "chart",
            "helmrelease",
            "lambda",
            "function",
            "faas",
            "knative",
            "kafka",
            "rabbitmq",
            "activemq",
            "nats",
            "pulsar",
            "mq",
            "queue",
            "bus",
            "rediscluster",
            "memcached",
            "prometheus",
            "grafana",
            "tempo",
            "loki",
            "jaeger",
            "tosca.nodes.SoftwareComponent",
        ],
        category=NodeCategory.SOFTWARE,
    ),
    # Database
    TypeRule(
        patterns=[
            "database",
            "db",
            "rdbms",
            "nosql",
            "datastore",
            "sql",
            "postgres",
            "mysql",
            "mariadb",
            "oracle",
            "sqlserver",
            "aurora",
            "cloudsql",
            "tidb",
            "mongodb",
            "redis",
            "cassandra",
            "dynamodb",
            "cosmosdb",
            "bigtable",
            "bigquery",
            "spanner",
            "neptune",
            "arangodb",
            "clickhouse",
            "timescaledb",
            "timeseriesdb",
            "tsdb",
            "elasticsearch",
            "opensearch",
            "elasticache",
            "memcache",
            "snowflake",
            "redshift",
            "greenplum",
            "vertica",
            "tosca.nodes.Database",
        ],
        category=NodeCategory.DATABASE,
    ),
]

CAPABILITY_RULES: list[CapabilityRule] = [
    CapabilityRule(  # Compute
        names_or_types=[
            "tosca.capabilities.compute",
            "compute",
            "scalable",
            "host",
            "container",
            "virtual_machine",
            "vm",
            "autoscale",
        ],
        category=NodeCategory.COMPUTE,
    ),
    CapabilityRule(  # Storage
        names_or_types=[
            "tosca.capabilities.storage",
            "storage",
            "volume",
            "attachment",
            "attachable",
            "block_storage",
            "object_storage",
            "mount",
            "shareable",
            "snapshot",
        ],
        category=NodeCategory.STORAGE,
    ),
    CapabilityRule(  # Network
        names_or_types=[
            "tosca.capabilities.network",
            "network",
            "linkable",
            "endpoint",
            "end_point",
            "connectivity",
            "bindable",
            "port",
            "serviceendpoint",
            "listener",
        ],
        category=NodeCategory.NETWORK,
    ),
    CapabilityRule(  # Database
        names_or_types=[
            "tosca.capabilities.endpoint.database",
            "database",
            "datasource",
            "db_endpoint",
            "rds",
            "sql_endpoint",
            "nosql_endpoint",
        ],
        category=NodeCategory.DATABASE,
    ),
    CapabilityRule(  # Software (catch-all)
        names_or_types=[
            "tosca.capabilities.softwarecomponent",
            "software",
            "service",
            "application",
            "microservice",
            "client",
            "agent",
            "runtime",
            "component",
        ],
        category=NodeCategory.SOFTWARE,
    ),
]


def infer_category(
    node_type: Optional[str],
    capabilities: Optional[Dict[str, Any]] = None,
) -> Optional[NodeCategory]:
    """
    Return a NodeCategory best-guess or None when nothing matches.
    """
    # 1) try type rules
    if node_type:
        node_type_lc = (
            node_type.lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )
        for t_rule in TYPE_RULES:
            if (cat := t_rule.match(node_type_lc)) is not None:
                logger.debug("category via type-rule → %s", cat)
                return cat

    # 2) try capability rules
    if capabilities:
        for c_rule in CAPABILITY_RULES:
            if (cat := c_rule.match(capabilities)) is not None:
                logger.debug("category via capability-rule → %s", cat)
                return cat

    # 3) give up
    logger.debug("unable to infer category for type=%s", node_type)
    return None
