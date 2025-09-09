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
        """Map aws_route53_record resource to dedicated TOSCA Network node.

        Creates a first-class DNS record node that captures:
        - DNS record semantics (name, type, TTL, alias configuration)
        - Explicit relationships to DNS zone and target resources
        - Comprehensive AWS Route53 metadata

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

        # Always create a dedicated DNS record node
        self._create_dns_record_node(
            resource_name, resource_type, resource_data, values, builder, context
        )

    def _create_dns_record_node(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Create a dedicated TOSCA Network node for the DNS record.

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

        # Extract DNS record properties
        dns_name = values.get("name")
        record_type = values.get("type", "").upper()
        ttl = values.get("ttl")
        alias_configs = values.get("alias", [])

        if not dns_name:
            logger.warning(
                "Route53 record '%s' has no name, skipping DNS record creation",
                resource_name,
            )
            return

        # Create Network node for the DNS record
        dns_node = builder.add_node(
            name=node_name,
            node_type="Network",
        )

        # Set DNS record properties - only use Network-compatible properties
        dns_properties = {
            "network_name": dns_name,
            "network_type": "dns_record",
        }

        dns_node.with_properties(dns_properties)

        # Build comprehensive metadata including DNS-specific properties
        metadata = self._build_dns_record_metadata(
            resource_type,
            clean_name,
            values,
            metadata_values,
            resource_data,
            record_type,
            ttl,
            alias_configs,
        )

        # Attach metadata to the node
        dns_node.with_metadata(metadata)

        # Add relationships to zone and target resources
        self._add_dns_record_relationships(
            dns_node, resource_data, values, metadata_values, builder, context
        )

        logger.info(
            "Successfully created DNS record node '%s' for Route53 record '%s' (%s)",
            node_name,
            dns_name,
            record_type,
        )

    def _build_dns_record_metadata(
        self,
        resource_type: str,
        clean_name: str,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        resource_data: dict[str, Any],
        record_type: str | None = None,
        ttl: int | None = None,
        alias_configs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build comprehensive metadata for the DNS record node.

        Args:
            resource_type: The resource type
            clean_name: Clean resource name without prefix
            values: Resolved values for properties
            metadata_values: Resolved values for metadata
            resource_data: Original resource data
            record_type: DNS record type (A, AAAA, CNAME, etc.)
            ttl: Time-to-live value for the DNS record
            alias_configs: Alias configuration list for the DNS record

        Returns:
            Dictionary containing metadata
        """
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "Route53DNSRecord"

        # Description
        record_name = values.get("name", "unknown")
        record_type = values.get("type", "unknown")
        metadata["description"] = (
            f"AWS Route53 DNS Record: {record_name} ({record_type})"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core Route53 Record properties - use metadata values for concrete resolution
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

        # DNS-specific properties that were moved from Network node properties
        if record_type:
            metadata["dns_record_type"] = record_type

        if ttl is not None:
            metadata["dns_ttl"] = ttl

        # Check if this is an alias record
        if alias_configs:
            metadata["dns_alias_enabled"] = True
        else:
            metadata["dns_alias_enabled"] = False

        return metadata

    def _add_dns_record_relationships(
        self,
        dns_node,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Add explicit relationships from DNS record to zone and target resources.

        Args:
            dns_node: The DNS record node to add relationships to
            resource_data: Complete resource data
            values: Resolved values for properties
            metadata_values: Resolved values for metadata
            builder: ServiceTemplateBuilder for accessing other nodes
            context: TerraformMappingContext for dependency resolution
        """
        # Add relationship to DNS zone
        if context:
            zone_node_name = self._find_zone_node_name(values, context, resource_data)
        else:
            zone_node_name = None
        if zone_node_name:
            dns_node.add_requirement("zone").to_node(zone_node_name).with_relationship(
                "DependsOn"
            ).and_node()
            logger.info(
                "Added zone requirement to '%s' for DNS record '%s'",
                zone_node_name,
                dns_node.name,
            )

        # Add relationship to target resource (if applicable)
        target_node_name = self._find_target_load_balancer(
            values, context, resource_data
        )
        if target_node_name:
            dns_node.add_requirement("target").to_node(
                target_node_name
            ).with_relationship("RoutesTo").and_node()
            logger.info(
                "Added target requirement to '%s' for DNS record '%s'",
                target_node_name,
                dns_node.name,
            )

            # Optional compatibility layer: add dns_name to target LoadBalancer
            self._add_compatibility_dns_name(
                target_node_name, values.get("name"), builder, context
            )

        # Add any additional terraform references as dependencies
        if context:
            terraform_refs = context.extract_terraform_references(resource_data)
            for prop_name, target_ref, relationship_type in terraform_refs:
                # Skip zone and target references we already handled
                if "route53_zone" in target_ref or "aws_lb." in target_ref:
                    continue

                if "." in target_ref:
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    dns_node.add_requirement(requirement_name).to_node(
                        target_node_name
                    ).with_relationship(relationship_type).and_node()

                    logger.info(
                        "Added %s requirement '%s' to DNS record '%s' "
                        "with relationship %s",
                        requirement_name,
                        target_node_name,
                        dns_node.name,
                        relationship_type,
                    )

    def _add_compatibility_dns_name(
        self,
        target_node_name: str,
        dns_name: str | None,
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Add dns_name property to target LoadBalancer for backward compatibility.

        This optional compatibility layer ensures existing consumers that expect
        dns_name properties on LoadBalancer client capabilities continue to work.

        Args:
            target_node_name: The TOSCA node name of the target LoadBalancer
            dns_name: The DNS name to add as a property
            builder: ServiceTemplateBuilder for accessing the target node
            context: TerraformMappingContext (unused but kept for consistency)
        """
        if not dns_name:
            logger.debug("No DNS name provided for compatibility layer")
            return

        # Add dns_name property to the target LoadBalancer's client capability
        try:
            lb_node = builder.get_node(target_node_name)
            if not lb_node:
                logger.warning(
                    "Could not find LoadBalancer node '%s' for DNS name '%s'",
                    target_node_name,
                    dns_name,
                )
                return

            # Access existing client capability or create one
            client_capability = lb_node.add_capability("client")
            client_capability.with_property("dns_name", dns_name).and_node()

            logger.info(
                "Compatibility layer: Added dns_name '%s' to LoadBalancer '%s'",
                dns_name,
                target_node_name,
            )
        except Exception as e:
            logger.warning(
                "Could not add compatibility dns_name '%s' to LoadBalancer '%s': %s",
                dns_name,
                target_node_name,
                e,
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

        # First try: Extract terraform references from zone_id (if context available)
        if context:
            terraform_refs = context.extract_terraform_references(
                {"values": {"zone_id": zone_id}}
            )
        else:
            terraform_refs = []

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

    def _find_target_load_balancer(
        self,
        values: dict[str, Any],
        context: "TerraformMappingContext | None",
        resource_data: dict[str, Any],
    ) -> str | None:
        """Find LoadBalancer that this Route53 record points to via alias config.

        Args:
            values: The resolved values from the resource data
            context: TerraformMappingContext for dependency resolution
            resource_data: Complete resource data

        Returns:
            The TOSCA node name for the target LoadBalancer or None if not found
        """
        if not context:
            logger.debug("No context provided for LoadBalancer lookup")
            return None

        # Look for alias configuration that points to a LoadBalancer
        alias_configs = values.get("alias", [])
        if not alias_configs:
            logger.debug("No alias configuration found in Route53 record")
            return None

        # Check each alias configuration for LoadBalancer references
        for alias in alias_configs:
            if not isinstance(alias, dict):
                continue

            # Look for name field that might reference a LoadBalancer
            alias_name = alias.get("name")
            if alias_name:
                # Extract terraform references from alias configuration
                terraform_refs = context.extract_terraform_references(
                    {"values": {"alias": [{"name": alias_name}]}}
                )

                for _, target_ref, _ in terraform_refs:
                    if "aws_lb." in target_ref:
                        # Found a LoadBalancer reference
                        tosca_node_name = BaseResourceMapper.generate_tosca_node_name(
                            target_ref, "aws_lb"
                        )
                        logger.debug(
                            "Found LoadBalancer reference: %s -> %s",
                            target_ref,
                            tosca_node_name,
                        )
                        return tosca_node_name

        # Fallback: Look in the resource configuration directly
        return self._find_load_balancer_from_configuration(resource_data, context)

    def _find_load_balancer_from_configuration(
        self,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext",
    ) -> str | None:
        """Find LoadBalancer reference from resource configuration (plan-only mode).

        Args:
            resource_data: Complete resource data
            context: TerraformMappingContext containing parsed data

        Returns:
            TOSCA node name for the LoadBalancer or None if not found
        """
        resource_address = resource_data.get("address")
        if not resource_address:
            return None

        # Look in the plan's configuration section
        parsed_data = context.parsed_data
        configuration = parsed_data.get("configuration", {})
        if not configuration:
            return None

        root_module = configuration.get("root_module", {})
        config_resources = root_module.get("resources", [])

        # Find our resource in configuration
        config_resource = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                config_resource = config_res
                break

        if not config_resource:
            return None

        # Extract references from alias expressions
        expressions = config_resource.get("expressions", {})
        alias_expressions = expressions.get("alias", [])

        for alias_expr in alias_expressions:
            if isinstance(alias_expr, dict):
                name_expr = alias_expr.get("name", {})
                if isinstance(name_expr, dict):
                    references = name_expr.get("references", [])
                    for ref in references:
                        if isinstance(ref, str) and "aws_lb." in ref:
                            # Extract LoadBalancer reference
                            # Extract LoadBalancer reference
                            lb_ref = ref.split(".dns_name")[0]
                            tosca_node_name = (
                                BaseResourceMapper.generate_tosca_node_name(
                                    lb_ref, "aws_lb"
                                )
                            )
                            logger.debug(
                                "Found LoadBalancer reference from config: %s -> %s",
                                lb_ref,
                                tosca_node_name,
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
