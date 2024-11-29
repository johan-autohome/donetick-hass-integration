"""Config flow for Donetick integration."""
from typing import Any
import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_URL, CONF_TOKEN
from .api import DonetickApiClient

class DonetickConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Donetick."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                client = DonetickApiClient(
                    user_input[CONF_URL],
                    user_input[CONF_TOKEN],
                    session,
                )
                # Test the API connection
                await client.async_get_tasks()

                return self.async_create_entry(
                    title="Donetick",
                    data=user_input
                )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Required(CONF_TOKEN): str,
            }),
            errors=errors,
        )