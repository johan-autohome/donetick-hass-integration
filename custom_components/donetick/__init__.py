"""The Donetick integration."""
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_URL, CONF_TOKEN, CONF_SHOW_DUE_IN
from .api import DonetickApiClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.TODO, Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TEXT]


SERVICE_COMPLETE_TASK = "complete_task"

COMPLETE_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): cv.positive_int,
    vol.Optional("completed_by"): cv.positive_int,
    vol.Optional("config_entry_id"): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Donetick from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_URL: entry.data[CONF_URL],
        CONF_TOKEN: entry.data[CONF_TOKEN],
        CONF_SHOW_DUE_IN: entry.data.get(CONF_SHOW_DUE_IN,7),
    }
    
    # Register service before setting up platforms
    async def complete_task_handler(call: ServiceCall) -> None:
        await async_complete_task_service(hass, call)
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_TASK,
        complete_task_handler,
        schema=COMPLETE_TASK_SCHEMA,
    )
    _LOGGER.debug("Registered service: %s.%s", DOMAIN, SERVICE_COMPLETE_TASK)
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_complete_task_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the complete_task service call."""
    task_id = call.data["task_id"]
    completed_by = call.data.get("completed_by")
    config_entry_id = call.data.get("config_entry_id")
    
    # Find the config entry to use
    entry = None
    if config_entry_id:
        # Check if it's a config entry ID
        entry = hass.config_entries.async_get_entry(config_entry_id)
        
        # If not found, check if it's an entity ID and extract config entry from it
        if not entry and config_entry_id.startswith("todo."):
            entity_registry = hass.helpers.entity_registry.async_get()
            entity_entry = entity_registry.async_get(config_entry_id)
            if entity_entry:
                entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
        
        if not entry:
            _LOGGER.error("Config entry not found for: %s", config_entry_id)
            return
    else:
        # Use the first Donetick integration if no specific entry provided
        entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)]
        if not entries:
            _LOGGER.error("No Donetick integration found")
            return
        entry = entries[0]
    
    # Get API client
    session = async_get_clientsession(hass)
    client = DonetickApiClient(
        hass.data[DOMAIN][entry.entry_id][CONF_URL],
        hass.data[DOMAIN][entry.entry_id][CONF_TOKEN],
        session,
    )
    
    try:
        result = await client.async_complete_task(task_id, completed_by)
        _LOGGER.info("Task %d completed successfully by user %s", task_id, completed_by or "default")
        
        # Trigger coordinator refresh for all todo entities
        entity_registry = hass.helpers.entity_registry.async_get()
        for entity_id in hass.states.async_entity_ids("todo"):
            if entity_id.startswith("todo.dt_"):
                entity_entry = entity_registry.async_get(entity_id)
                if entity_entry and entity_entry.config_entry_id == entry.entry_id:
                    # Trigger update - this will refresh the coordinator
                    await hass.helpers.entity_component.async_update_entity(entity_id)
                    
    except Exception as e:
        _LOGGER.error("Failed to complete task %d: %s", task_id, e)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove service if this is the last config entry
        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK):
            hass.services.async_remove(DOMAIN, SERVICE_COMPLETE_TASK)
            _LOGGER.debug("Removed service: %s.%s", DOMAIN, SERVICE_COMPLETE_TASK)
    
    return unload_ok