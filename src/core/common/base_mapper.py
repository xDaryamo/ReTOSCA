import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..protocols import ResourceMapper, SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class BaseResourceMapper(ResourceMapper, ABC):
    """
    Base class for resource mappers acting as a dispatcher.

    Provides common logic for registering and delegating to "SingleResourceMapper",
    keeping the technology-specific extraction logic abstracted.

    Subclasses must implement:
    - _extract_resources(): Logic for finding and iterating over resources
      within the technology-specific data structure (e.g., Terraform, Ansible).
    """

    def __init__(self):
        """Initializes the mapper and the strategy registry."""
        self._logger = logger.getChild(self.__class__.__name__)
        self._mappers: dict[str, SingleResourceMapper] = {}

    @staticmethod
    def generate_tosca_node_name(resource_name: str, resource_type: str) -> str:
        """
        Genera un nome di nodo TOSCA univoco basato sul nome e tipo della risorsa.

        Converte nomi come "aws_instance.web" in "aws_instance_web" per evitare
        conflitti di nomi tra risorse di tipo diverso ma con lo stesso nome.

        Args:
            resource_name: Nome completo della risorsa (es. "aws_instance.web")
            resource_type: Tipo della risorsa (es. "aws_instance")

        Returns:
            Nome del nodo TOSCA univoco (es. "aws_instance_web")
        """
        # Estrai il nome pulito dalla risorsa (rimuovi il prefisso del tipo)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Pulisci il nome per renderlo un nome di nodo TOSCA valido
        clean_name = clean_name.replace("-", "_").replace("[", "_").replace("]", "")

        # Crea il nome composto con il prefisso del tipo di risorsa
        tosca_node_name = f"{resource_type}_{clean_name}"

        return tosca_node_name

    # --- Protocol Implementation (Common Logic) ---

    def register_mapper(self, resource_type: str, mapper: SingleResourceMapper) -> None:
        """
        Registers a specific mapper for a resource type.
        This is the common logic of the Registry pattern.
        """
        if resource_type in self._mappers:
            self._logger.warning(
                f"Overwriting mapper for resource type: '{resource_type}'"
            )
        self._logger.info(
            f"Registering mapper '{mapper.__class__.__name__}' "
            f"for type '{resource_type}'"
        )

        self._mappers[resource_type] = mapper

    def get_registered_mappers(self) -> dict[str, SingleResourceMapper]:
        """Returns the dictionary of registered mappers."""
        return self._mappers

    def map(
        self, parsed_data: dict[str, Any], builder: "ServiceTemplateBuilder"
    ) -> None:
        """
        Orchestrates the mapping using the Template Method pattern.

        1. Calls the abstract method `_extract_resources` to obtain resources.
        2. Iterates over them and delegates to the correct mapper
           found in the registry.
        """

        self._logger.info("Starting the resource mapping process.")
        try:
            # Delegates to the subclass to find the resources
            resources = self._extract_resources(parsed_data)

            for resource_name, resource_type, resource_data in resources:
                mapper_strategy = self._mappers.get(resource_type)

                if mapper_strategy:
                    # Uses can_map for a finer check
                    if mapper_strategy.can_map(resource_type, resource_data):
                        self._logger.debug(
                            f"Mapping resource '{resource_name}' ({resource_type})"
                        )
                        # Delegates work to the specific strategy class
                        mapper_strategy.map_resource(
                            resource_name, resource_type, resource_data, builder
                        )
                    else:
                        self._logger.warning(
                            f"The mapper for '{resource_type}' cannot handle "
                            f"the specific configuration of '{resource_name}'. "
                            "Skipping."
                        )

                else:
                    self._logger.warning(
                        f"No mapper registered for resource type: '{resource_type}'. "
                        "Skipping."
                    )

            self._logger.info("Resource mapping process completed.")

        except Exception as e:
            self._logger.error(f"Critical failure during mapping: {e}", exc_info=True)
            raise

    # --- Abstract Method (Technology-Specific Logic) ---

    @abstractmethod
    def _extract_resources(
        self, parsed_data: dict[str, Any]
    ) -> Iterable[tuple[str, str, dict[str, Any]]]:
        """
        Technology-specific method to extract resources.

        Must be implemented by every subclass
        to navigate the specific data structure and produce an iterable of resources.

        Args:
            parsed_data: The dictionary of data coming from the parser.

        Yields:
            A tuple for each found resource, containing:
            (resource_name, resource_type, resource_data)
        """
        pass
