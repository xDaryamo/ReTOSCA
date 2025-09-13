"""Plugin registry for managing available phase plugins."""

import logging
from typing import Any

from .protocols import PhasePlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Registry for managing available phase plugins.

    Maps plugin type names to their corresponding plugin classes,
    enabling dynamic plugin discovery and instantiation.
    """

    def __init__(self):
        """Initialize the plugin registry."""
        self._plugins: dict[str, type[PhasePlugin]] = {}
        self._logger = logger.getChild(self.__class__.__name__)

    def register_plugin(
        self, plugin_type: str, plugin_class: type[PhasePlugin]
    ) -> None:
        """
        Register a plugin class with a type name.

        Args:
            plugin_type: The type identifier for the plugin
                        (e.g., 'terraform', 'ansible')
            plugin_class: The plugin class to register

        Raises:
            ValueError: If plugin_type is empty or plugin_class is invalid
        """
        if not plugin_type or not plugin_type.strip():
            raise ValueError("Plugin type cannot be empty")

        if not plugin_class:
            raise ValueError("Plugin class cannot be None")

        plugin_type = plugin_type.strip().lower()

        if plugin_type in self._plugins:
            self._logger.warning(
                f"Overwriting existing plugin registration for type '{plugin_type}'"
            )

        self._plugins[plugin_type] = plugin_class
        self._logger.info(
            f"Registered plugin '{plugin_class.__name__}' for type '{plugin_type}'"
        )

    def get_plugin_class(self, plugin_type: str) -> type[PhasePlugin]:
        """
        Get the plugin class for a given type.

        Args:
            plugin_type: The plugin type to look up

        Returns:
            The plugin class for the given type

        Raises:
            ValueError: If the plugin type is not registered
        """
        if not plugin_type:
            raise ValueError("Plugin type cannot be empty")

        plugin_type = plugin_type.strip().lower()

        if plugin_type not in self._plugins:
            available_types = list(self._plugins.keys())
            available_str = ", ".join(available_types) if available_types else "none"
            raise ValueError(
                f"Unknown plugin type '{plugin_type}'. "
                f"Available types: {available_str}"
            )

        return self._plugins[plugin_type]

    def create_plugin_instance(self, plugin_type: str) -> PhasePlugin:
        """
        Create an instance of the plugin for the given type.

        Args:
            plugin_type: The plugin type to instantiate

        Returns:
            A new instance of the plugin

        Raises:
            ValueError: If the plugin type is not registered
            RuntimeError: If plugin instantiation fails
        """
        plugin_class = self.get_plugin_class(plugin_type)

        try:
            return plugin_class()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create instance of plugin '{plugin_class.__name__}' "
                f"for type '{plugin_type}': {e}"
            ) from e

    def get_available_types(self) -> list[str]:
        """
        Get a list of all available plugin types.

        Returns:
            List of registered plugin type names
        """
        return sorted(self._plugins.keys())

    def is_type_available(self, plugin_type: str) -> bool:
        """
        Check if a plugin type is available.

        Args:
            plugin_type: The plugin type to check

        Returns:
            True if the plugin type is registered, False otherwise
        """
        if not plugin_type:
            return False

        return plugin_type.strip().lower() in self._plugins

    def get_plugin_info(self, plugin_type: str) -> dict[str, Any]:
        """
        Get information about a registered plugin.

        Args:
            plugin_type: The plugin type to get info for

        Returns:
            Dictionary with plugin information

        Raises:
            ValueError: If the plugin type is not registered
        """
        plugin_class = self.get_plugin_class(plugin_type)

        # Try to get plugin info from an instance
        try:
            instance = self.create_plugin_instance(plugin_type)
            return instance.get_plugin_info()
        except Exception as e:
            self._logger.warning(
                f"Could not get plugin info from instance for '{plugin_type}': {e}"
            )
            # Fallback to basic class info
            return {
                "name": plugin_class.__name__,
                "type": plugin_type,
                "class": plugin_class.__module__ + "." + plugin_class.__qualname__,
                "error": f"Could not instantiate: {e}",
            }

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()
        self._logger.info("Cleared all plugin registrations")

    def __len__(self) -> int:
        """Return the number of registered plugins."""
        return len(self._plugins)

    def __contains__(self, plugin_type: str) -> bool:
        """Check if a plugin type is registered (supports 'in' operator)."""
        return self.is_type_available(plugin_type)


# Global plugin registry instance
_global_registry = PluginRegistry()


def get_global_registry() -> PluginRegistry:
    """Get the global plugin registry instance."""
    return _global_registry


def register_builtin_plugins() -> None:
    """Register all built-in plugins with the global registry."""
    # Import here to avoid circular imports
    from src.plugins.provisioning.terraform.terraform_plugin import (
        TerraformProvisioningPlugin,
    )

    registry = get_global_registry()

    # Only register if not already registered to avoid duplicate warnings
    if not registry.is_type_available("terraform"):
        registry.register_plugin("terraform", TerraformProvisioningPlugin)
