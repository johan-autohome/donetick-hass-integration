"""Todo for Donetick integration."""
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature, 
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_URL, CONF_TOKEN, CONF_SHOW_DUE_IN
from .api import DonetickApiClient
from .model import DonetickTask

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Donetick todo platform."""
    session = async_get_clientsession(hass)
    client = DonetickApiClient(
        hass.data[DOMAIN][config_entry.entry_id][CONF_URL],
        hass.data[DOMAIN][config_entry.entry_id][CONF_TOKEN],
        session,
    )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="donetick_todo",
        update_method=client.async_get_tasks,
        update_interval=timedelta(minutes=15),
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([DonetickTodoListEntity(coordinator, config_entry)])

class DonetickTodoListEntity(CoordinatorEntity, TodoListEntity):
    """Donetick Todo List entity."""
    
    _attr_supported_features = (
        TodoListEntityFeature.UPDATE_TODO_ITEM
        # TodoListEntityFeature.CREATE_TODO_ITEM
        # | TodoListEntityFeature.DELETE_TODO_ITEM
        # | TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the Todo List."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}"

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return a list of todo items."""
        if self.coordinator.data is None:
            return []
        return [  TodoItem(
            summary=task.name,
            # work around so homeassistant thinks the task is unique
            # if the task is recurring, the id will be the same, so we add the next due date to the id
            # this way, homeassistant will think it's a different task and have it unchecked
            uid="%s--%s" % (task.id, task.next_due_date),
            status=self.get_status(task.next_due_date, task.is_active),
            due=task.next_due_date,
            description=f"{task.id} Frequency: {task.frequency} {task.frequency_type}\nLabels: {task.labels}"
        ) for task in self.coordinator.data if task.is_active ]

    def get_status(self, due_date: datetime, is_active: bool) -> TodoItemStatus:
        """Return the status of the task."""
        if not is_active:
            return TodoItemStatus.COMPLETED
        return TodoItemStatus.NEEDS_ACTION 

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a todo item."""
        # Implement API call to create item
        await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a todo item."""
        _LOGGER.debug("Update todo item: %s %s", item.uid, item.status)
        if not self.coordinator.data:
            return None
        _LOGGER.debug("Updating task %s, current status is %s", item.uid, item.status)
        if item.status == TodoItemStatus.COMPLETED:
            try:
                session = async_get_clientsession(self.hass)
                client = DonetickApiClient(
                    self._config_entry.data[CONF_URL],
                    self._config_entry.data[CONF_TOKEN],
                    session,
                )
                # Complete the task
                res = await client.async_complete_task(item.uid.split("--")[0])
                if res.frequency_type!= "once":
                    _LOGGER.debug("Task %s is recurring, updating next due date", res.name)
                    item.status = TodoItemStatus.NEEDS_ACTION
                    item.due = res.next_due_date
                    self.async_update_todo_item(item)


            except Exception as e:
                _LOGGER.error("Error completing task from Donetick: %s", e)
        else:
            pass
 
        await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        # Implement API call to delete items
        await self.coordinator.async_refresh()

    async def async_get_todo_items(self) -> list[TodoItem]:
        """Get all todo items."""
        return self.todo_items
