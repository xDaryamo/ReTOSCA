from __future__ import annotations

import pytest

from src.plugins.terraform.context import (
    DependencyFilter,
    TerraformMappingContext,
)
from src.plugins.terraform.variables import VariableContext

# ---------------------------------------------------------------------------
# Fixture: parsed_data completo per testare:
# - estrazione reference da configuration + depends_on
# - risoluzione indirizzi con/ senza indice
# - pattern property (vpc_id -> aws_vpc)
# - integrazione con VariableContext per get_resolved_values
# ---------------------------------------------------------------------------


@pytest.fixture()
def parsed_data() -> dict:
    return {
        # ---- Per VariableContext (definizioni + planned_values del "plan") ----
        "plan": {
            "configuration": {
                "root_module": {
                    "variables": {
                        "cidr_map": {
                            "type": "map(string)",
                            "default": {
                                "private0": "10.0.1.0/24",
                                "private1": "10.0.2.0/24",
                            },
                        },
                    },
                    "resources": [
                        {
                            "address": "aws_nat_gateway.main[1]",
                            "expressions": {
                                # ref non indicizzato verso risorsa indicizzata
                                "subnet_id": {"references": ["aws_subnet.private.id"]},
                                "allocation_id": {"references": ["aws_eip.nat[1].id"]},
                            },
                        },
                        {
                            "address": "aws_route.igw_route",
                            "expressions": {
                                "gateway_id": {
                                    "references": ["aws_internet_gateway.igw.id"]
                                },
                                "route_table_id": {
                                    "references": ["aws_route_table.rt.id"]
                                },
                                "destination_cidr_block": {},
                            },
                        },
                        {
                            "address": "aws_subnet.private[0]",
                            "expressions": {
                                # variabile di tipo map
                                "cidr_block": {"references": ["var.cidr_map"]}
                            },
                        },
                        {"address": "aws_subnet.private[1]", "expressions": {}},
                        {"address": "aws_route_table.rt", "expressions": {}},
                        {"address": "aws_internet_gateway.igw", "expressions": {}},
                        {"address": "aws_vpc.main", "expressions": {}},
                    ],
                }
            },
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_subnet.private[0]",
                            "values": {
                                "id": "subnet-aaa",
                                "vpc_id": "vpc-123",
                                "cidr_block": "10.0.1.0/24",
                            },
                        },
                        {
                            "address": "aws_subnet.private[1]",
                            "values": {"id": "subnet-bbb", "vpc_id": "vpc-123"},
                        },
                        {
                            "address": "aws_nat_gateway.main[1]",
                            "values": {"subnet_id": "subnet-bbb", "vpc_id": "vpc-123"},
                        },
                        {
                            "address": "aws_eip.nat[1]",
                            "values": {"id": "eipalloc-11", "public_ip": "1.2.3.5"},
                        },
                        {"address": "aws_route_table.rt", "values": {"id": "rtb-001"}},
                        {
                            "address": "aws_internet_gateway.igw",
                            "values": {"id": "igw-123"},
                        },
                        {
                            "address": "aws_vpc.main",
                            "values": {"id": "vpc-123", "cidr_block": "10.0.0.0/16"},
                        },
                    ]
                }
            },
        },
        # ---- Per TerraformMappingContext (ricerca veloce in planned_values) ----
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_subnet.private[0]",
                        "values": {"id": "subnet-aaa", "vpc_id": "vpc-123"},
                    },
                    {
                        "address": "aws_subnet.private[1]",
                        "values": {"id": "subnet-bbb", "vpc_id": "vpc-123"},
                    },
                    {
                        "address": "aws_nat_gateway.main[1]",
                        "values": {"subnet_id": "subnet-bbb", "vpc_id": "vpc-123"},
                    },
                    {"address": "aws_eip.nat[1]", "values": {"id": "eipalloc-11"}},
                    {"address": "aws_route_table.rt", "values": {"id": "rtb-001"}},
                    {
                        "address": "aws_internet_gateway.igw",
                        "values": {"id": "igw-123"},
                    },
                    {"address": "aws_vpc.main", "values": {"id": "vpc-123"}},
                ]
            }
        },
        # ---- Stato sintetico per pattern vpc_id -> aws_vpc.main ----
        "state": {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "type": "aws_vpc",
                            "address": "aws_vpc.main",
                            "values": {"id": "vpc-123"},
                        },
                        {
                            "type": "aws_subnet",
                            "address": "aws_subnet.private[0]",
                            "values": {"id": "subnet-aaa"},
                        },
                        {
                            "type": "aws_subnet",
                            "address": "aws_subnet.private[1]",
                            "values": {"id": "subnet-bbb"},
                        },
                        {
                            "type": "aws_internet_gateway",
                            "address": "aws_internet_gateway.igw",
                            "values": {"id": "igw-123"},
                        },
                        {
                            "type": "aws_route_table",
                            "address": "aws_route_table.rt",
                            "values": {"id": "rtb-001"},
                        },
                        {
                            "type": "aws_nat_gateway",
                            "address": "aws_nat_gateway.main[1]",
                            "values": {"id": "nat-999"},
                        },
                        {
                            "type": "aws_eip",
                            "address": "aws_eip.nat[1]",
                            "values": {"id": "eipalloc-11"},
                        },
                    ]
                }
            }
        },
    }


# ---------------------------------------------------------------------------
# Test: parsing e generazione nomi da indirizzo Terraform
# ---------------------------------------------------------------------------


def test_parse_and_generate_names():
    comps = TerraformMappingContext.parse_terraform_resource_address(
        "module.vpc.aws_nat_gateway.this[1]"
    )
    assert comps["module"] == "module.vpc"
    assert comps["type"] == "aws_nat_gateway"
    assert comps["name"] == "this"
    assert comps["index"] == "1"

    name = TerraformMappingContext.generate_tosca_node_name_from_address(
        "module.vpc.aws_nat_gateway.this[1]"
    )
    assert name == "module_vpc_aws_nat_gateway_this_1"

    simple = TerraformMappingContext.generate_tosca_node_name_from_address(
        "aws_subnet.private[0]"
    )
    assert simple == "aws_subnet_private_0"


# ---------------------------------------------------------------------------
# Test: estrazione reference (configuration + depends_on) e risoluzione nomi
# ---------------------------------------------------------------------------


def test_extract_references_and_resolve(parsed_data):
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=None)

    # resource_data tipico da state/ planned_values con depends_on
    resource_data = {
        "address": "aws_nat_gateway.main[1]",
        "values": {"vpc_id": "vpc-123"},
        "depends_on": ["aws_eip.nat[1]"],  # deve produrre una dipendenza
    }

    refs = ctx.extract_terraform_references(resource_data)

    # Ci aspettiamo:
    # - subnet_id -> aws_subnet.private (risolto con indice 1)
    #   -> tosca "aws_subnet_private_1"
    # - dependency -> aws_eip.nat[1] -> tosca "aws_eip_nat_1"
    targets = {t for _, t, _ in refs}
    assert "aws_subnet_private_1" in targets
    assert "aws_eip_nat_1" in targets

    # Relazione per subnet_id è DependsOn
    subnet_props = ("subnet_id", "ref_subnet_id")
    rel_for_subnet = {rel for prop, _, rel in refs if prop in subnet_props}
    assert "DependsOn" in rel_for_subnet


# ---------------------------------------------------------------------------
# Test: filtro dipendenze (exclude target types)
# ---------------------------------------------------------------------------


def test_filtered_references_excludes_igw(parsed_data):
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=None)

    resource_data = {
        "address": "aws_route.igw_route",
        "values": {},
    }

    # Escludiamo qualsiasi dipendenza verso aws_internet_gateway
    df = DependencyFilter(exclude_target_types={"aws_internet_gateway"})
    refs = ctx.extract_filtered_terraform_references(resource_data, df)

    targets = {t for _, t, _ in refs}
    # Deve rimanere solo la route table
    assert "aws_route_table_rt" in targets
    assert not any("internet_gateway" in t for t in targets)


# ---------------------------------------------------------------------------
# Test: pattern da valori (vpc_id -> aws_vpc.main)
# ---------------------------------------------------------------------------


def test_property_pattern_vpc_id(parsed_data):
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=None)

    resource_data = {
        "address": "aws_subnet.private[0]",
        "values": {"vpc_id": "vpc-123"},
        # niente depends_on -> abilita pattern detection
    }

    refs = ctx.extract_terraform_references(resource_data)
    # Deve comparire ref alla VPC
    assert any(t.endswith("aws_vpc_main") for _, t, _ in refs) or any(
        t == "aws_vpc_main" for _, t, _ in refs
    )


# ---------------------------------------------------------------------------
# Test: risoluzione ref con contesto array (sorgente indicizzato, ref non indicizzato)
# ---------------------------------------------------------------------------


def test_resolve_array_reference_with_context(parsed_data):
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=None)
    resource_data = {"address": "aws_nat_gateway.main[1]", "values": {}}

    tosca = ctx.resolve_array_reference_with_context(
        resource_data, "aws_subnet.private"
    )
    assert tosca == "aws_subnet_private_1"


# ---------------------------------------------------------------------------
# Test: integrazione con VariableContext per get_resolved_values
# ---------------------------------------------------------------------------


def test_get_resolved_values_with_variable_context(parsed_data):
    var_ctx = VariableContext(parsed_data)
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=var_ctx)

    # Valori della subnet[0] hanno cidr_block che matcha cidr_map["private0"]
    resource_data = {
        "address": "aws_subnet.private[0]",
        "values": {"cidr_block": "10.0.1.0/24"},
    }

    # In "property" deve usare $get_input
    resolved_props = ctx.get_resolved_values(resource_data, context="property")
    assert resolved_props["cidr_block"] == {"$get_input": ["cidr_map", "private0"]}

    # In "metadata" deve restare concreto
    resolved_meta = ctx.get_resolved_values(resource_data, context="metadata")
    assert resolved_meta["cidr_block"] == "10.0.1.0/24"


# ---------------------------------------------------------------------------
# Test: risoluzione diretta di un riferimento (senza indice) al primo match
# ---------------------------------------------------------------------------


def test_resolve_terraform_reference_to_tosca_node(parsed_data):
    ctx = TerraformMappingContext(parsed_data=parsed_data, variable_context=None)

    # Senza indice: il matcher può risolvere al primo elemento trovato ([0])
    name_unindexed = ctx.resolve_terraform_reference_to_tosca_node("aws_subnet.private")
    assert name_unindexed in {"aws_subnet_private_0", "aws_subnet_private_1"}

    # Con indice esplicito
    name_indexed = ctx.resolve_terraform_reference_to_tosca_node(
        "aws_subnet.private[1]"
    )
    assert name_indexed == "aws_subnet_private_1"
