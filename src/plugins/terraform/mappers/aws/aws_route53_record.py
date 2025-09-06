import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSRoute53RecordMapper(SingleResourceMapper):
    """Map a Terraform 'aws_route53_record' resource to appropriate TOSCA nodes.

    AWS Route53 DNS records are mapped to different TOSCA node types based on
    their purpose:
    1. Simple DNS records (A/AAAA/CNAME) → Endpoint or Endpoint.Public nodes
    2. Load balancing records (with routing policies) → LoadBalancer nodes

    This distinction allows for better modeling of DNS-based load balancing
    scenarios versus simple domain name resolution.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_route53_record'."""
        _ = resource_data  # Parameter required by protocol but not used
        return resource_type == "aws_route53_record"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map aws_route53_record resource to appropriate TOSCA node type.

        Based on the record configuration:
        - Simple DNS records (A/AAAA/CNAME) → Endpoint or Endpoint.Public nodes
        - Load balancing records → LoadBalancer nodes

        Args:
            resource_name: resource name (e.g. 'aws_route53_record.www')
            resource_type: resource type (always 'aws_route53_record')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution and
                dependency analysis
        """
        logger.info("Mapping Route53 DNS Record resource: '%s'", resource_name)

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})

        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Determine the appropriate TOSCA node type based on record configuration
        is_load_balancer = self._is_load_balancing_record(values)

        if is_load_balancer:
            self._map_as_load_balancer(
                resource_name, resource_type, resource_data, values, builder, context
            )
        else:
            self._map_as_endpoint(
                resource_name, resource_type, resource_data, values, builder, context
            )

    def _is_load_balancing_record(self, values: dict[str, Any]) -> bool:
        """Determine if this is a load balancing record based on routing policies.

        Args:
            values: The resolved values from the resource data

        Returns:
            True if the record has routing policies (load balancing), False otherwise
        """
        # Check for any routing policy configuration
        routing_policies = [
            "weighted_routing_policy",
            "latency_routing_policy",
            "geolocation_routing_policy",
            "geoproximity_routing_policy",
            "failover_routing_policy",
            "cidr_routing_policy",
        ]

        for policy in routing_policies:
            if values.get(policy):
                return True

        # Also check for set_identifier which usually indicates routing policies
        if values.get("set_identifier"):
            return True

        return False

    def _map_as_load_balancer(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map the Route53 record as a LoadBalancer node.

        Args:
            resource_name: resource name (e.g. 'aws_route53_record.www')
            resource_type: resource type (always 'aws_route53_record')
            resource_data: resource data from the Terraform plan
            values: resolved values for properties
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        # Generate a unique TOSCA node name
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Extract the clean name for metadata
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Get resolved values specifically for metadata
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Create LoadBalancer node
        lb_node = builder.add_node(
            name=node_name,
            node_type="LoadBalancer",
        )

        # Build metadata
        metadata = self._build_metadata(
            resource_type, clean_name, values, metadata_values, resource_data
        )
        metadata["aws_component_type"] = "Route53LoadBalancer"
        metadata["description"] = (
            f"AWS Route53 Load Balancer: {values.get('name', 'unknown')} "
            f"({values.get('type', 'unknown')})"
        )

        # Attach metadata
        lb_node.with_metadata(metadata)

        # Configure client capability with network_name for DNS zone
        zone_info = self._extract_zone_info(values, metadata_values, context)

        # Set network_name based on the DNS zone
        network_name = zone_info.get("zone_name", "PUBLIC")

        # Configure the client capability
        client_capability = lb_node.add_capability("client")
        if network_name:
            client_capability.with_property("network_name", network_name)

        # Set protocol based on record type
        record_type = values.get("type", "").upper()
        if record_type in ["A", "AAAA"]:
            client_capability.with_property("protocol", "http")
        elif record_type == "CNAME":
            client_capability.with_property("protocol", "http")

        client_capability.and_node()

        # Configure algorithm based on routing policy
        algorithm = self._determine_algorithm(values)
        if algorithm:
            lb_node.with_property("algorithm", algorithm)

        logger.info(
            "Successfully created LoadBalancer node '%s' for Route53 record '%s'",
            node_name,
            values.get("name", resource_name),
        )

    def _map_as_endpoint(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map the Route53 record as an Endpoint node.

        Args:
            resource_name: resource name (e.g. 'aws_route53_record.www')
            resource_type: resource type (always 'aws_route53_record')
            resource_data: resource data from the Terraform plan
            values: resolved values for properties
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        # Generate a unique TOSCA node name
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Extract the clean name for metadata
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Get resolved values specifically for metadata
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Determine if this should be public or private endpoint
        record_name = values.get("name", "")
        is_public = self._is_public_endpoint(record_name, values)

        endpoint_type = "Endpoint.Public" if is_public else "Endpoint"

        # Create Endpoint node
        endpoint_node = builder.add_node(
            name=node_name,
            node_type=endpoint_type,
        )

        # Build metadata
        metadata = self._build_metadata(
            resource_type, clean_name, values, metadata_values, resource_data
        )
        metadata["aws_component_type"] = "Route53Endpoint"
        metadata["description"] = (
            f"AWS Route53 DNS Endpoint: {values.get('name', 'unknown')} "
            f"({values.get('type', 'unknown')})"
        )

        # Attach metadata
        endpoint_node.with_metadata(metadata)

        # Set protocol based on record type
        record_type = values.get("type", "").upper()
        if record_type in ["A", "AAAA"]:
            endpoint_node.with_property("protocol", "http")
        elif record_type == "CNAME":
            endpoint_node.with_property("protocol", "http")

        # Add link requirement to DNS zone if context is available
        if context:
            zone_node_name = self._find_zone_node_name(values, context, resource_data)
            if zone_node_name:
                (
                    endpoint_node.add_requirement("link")
                    .to_node(zone_node_name)
                    .to_capability("link")
                    .with_relationship("LinksTo")
                    .and_node()
                )
                logger.info(
                    "Added link requirement from '%s' to DNS zone '%s'",
                    node_name,
                    zone_node_name,
                )

        logger.info(
            "Successfully created %s node '%s' for Route53 record '%s'",
            endpoint_type,
            node_name,
            values.get("name", resource_name),
        )

    def _build_metadata(
        self,
        resource_type: str,
        clean_name: str,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        resource_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build comprehensive metadata for the node.

        Args:
            resource_type: The resource type
            clean_name: Clean resource name without prefix
            values: Resolved values for properties
            metadata_values: Resolved values for metadata
            resource_data: Original resource data

        Returns:
            Dictionary containing metadata
        """
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core Route53 Record properties
        for prop, aws_key in [
            ("name", "aws_record_name"),
            ("type", "aws_record_type"),
            ("zone_id", "aws_zone_id"),
            ("ttl", "aws_ttl"),
            ("records", "aws_records"),
            ("set_identifier", "aws_set_identifier"),
            ("health_check_id", "aws_health_check_id"),
            ("multivalue_answer", "aws_multivalue_answer"),
            ("allow_overwrite", "aws_allow_overwrite"),
            ("fqdn", "aws_fqdn"),
            ("id", "aws_record_id"),
        ]:
            value = metadata_values.get(prop)
            if value is not None:
                metadata[aws_key] = value

        # Routing policies
        self._process_routing_policies(metadata_values, metadata)

        # Alias configuration
        alias_config = metadata_values.get("alias", [])
        if alias_config:
            metadata["aws_alias_configuration"] = alias_config

        return metadata

    def _extract_zone_info(
        self,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext | None",
    ) -> dict[str, Any]:
        """Extract zone information for network_name configuration.

        Args:
            values: Resolved values for properties
            metadata_values: Resolved values for metadata
            context: TerraformMappingContext for dependency resolution

        Returns:
            Dictionary with zone information
        """
        zone_info = {}

        # Try to find the zone name from context or metadata
        zone_id = values.get("zone_id") or metadata_values.get("zone_id")
        if zone_id and context:
            # Try to resolve the zone reference to get the zone name
            terraform_refs = context.extract_terraform_references(
                {"values": {"zone_id": zone_id}}
            )
            for _, target_ref, _ in terraform_refs:
                if "route53_zone" in target_ref:
                    # Found a reference to a Route53 zone
                    zone_info["zone_reference"] = target_ref
                    break

        # Use a sensible default
        zone_info["zone_name"] = "PUBLIC"

        return zone_info

    def _determine_algorithm(self, values: dict[str, Any]) -> str | None:
        """Determine load balancing algorithm based on routing policies.

        Args:
            values: The resolved values from the resource data

        Returns:
            Load balancing algorithm name or None
        """
        if values.get("weighted_routing_policy"):
            return "weighted"
        elif values.get("latency_routing_policy"):
            return "least_connections"
        elif values.get("geolocation_routing_policy"):
            return "geolocation"
        elif values.get("failover_routing_policy"):
            return "failover"

        return "round_robin"  # Default

    def _is_public_endpoint(self, record_name: str, values: dict[str, Any]) -> bool:
        """Determine if this should be a public endpoint.

        Args:
            record_name: The DNS record name
            values: The resolved values from the resource data

        Returns:
            True if this should be a public endpoint
        """
        # Consider it public if it's a common public subdomain
        public_patterns = ["www", "api", "app", "web", "portal", ""]

        if record_name in public_patterns:
            return True

        # If it's an A or AAAA record, likely public
        record_type = values.get("type", "").upper()
        if record_type in ["A", "AAAA"]:
            return True

        return False

    def _find_zone_node_name(
        self,
        values: dict[str, Any],
        context: "TerraformMappingContext",
        resource_data: dict[str, Any],
    ) -> str | None:
        """Find the TOSCA node name for the DNS zone.

        Args:
            values: The resolved values from the resource data
            context: TerraformMappingContext for dependency resolution
            resource_data: Complete resource data with depends_on information

        Returns:
            The TOSCA node name for the zone or None if not found
        """
        zone_id = values.get("zone_id")
        if not zone_id:
            return None

        # First try: Extract terraform references from the zone_id property
        terraform_refs = context.extract_terraform_references(
            {"values": {"zone_id": zone_id}}
        )

        for _, target_ref, _ in terraform_refs:
            if "route53_zone" in target_ref:
                tosca_node_name = BaseResourceMapper.generate_tosca_node_name(
                    target_ref, "aws_route53_zone"
                )
                return tosca_node_name

        # Second try: Look in depends_on for Route53 zone dependencies
        depends_on = resource_data.get("depends_on", [])
        for dependency in depends_on:
            if "route53_zone" in dependency:
                tosca_node_name = BaseResourceMapper.generate_tosca_node_name(
                    dependency, "aws_route53_zone"
                )
                return tosca_node_name

        return None

    def _process_routing_policies(
        self, metadata_values: dict[str, Any], metadata: dict[str, Any]
    ) -> None:
        """Process and extract routing policy configurations.

        Args:
            metadata_values: The resolved metadata values
            metadata: The metadata dictionary to update
        """
        # Weighted routing policy
        weighted_routing = metadata_values.get("weighted_routing_policy", [])
        if weighted_routing:
            metadata["aws_weighted_routing_policy"] = weighted_routing

        # Latency routing policy
        latency_routing = metadata_values.get("latency_routing_policy", [])
        if latency_routing:
            metadata["aws_latency_routing_policy"] = latency_routing

        # Geolocation routing policy
        geolocation_routing = metadata_values.get("geolocation_routing_policy", [])
        if geolocation_routing:
            metadata["aws_geolocation_routing_policy"] = geolocation_routing

        # Geoproximity routing policy
        geoproximity_routing = metadata_values.get("geoproximity_routing_policy", [])
        if geoproximity_routing:
            metadata["aws_geoproximity_routing_policy"] = geoproximity_routing

        # Failover routing policy
        failover_routing = metadata_values.get("failover_routing_policy", [])
        if failover_routing:
            metadata["aws_failover_routing_policy"] = failover_routing

        # CIDR routing policy
        cidr_routing = metadata_values.get("cidr_routing_policy", [])
        if cidr_routing:
            metadata["aws_cidr_routing_policy"] = cidr_routing
