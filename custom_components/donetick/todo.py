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

from .const import DOMAIN, CONF_URL, CONF_TOKEN, CONF_SHOW_DUE_IN, CONF_CREATE_UNIFIED_LIST, CONF_CREATE_ASSIGNEE_LISTS
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

    entities = []
    
    # Create unified list if enabled
    if config_entry.data.get(CONF_CREATE_UNIFIED_LIST, True):
        entities.append(DonetickAllTasksList(coordinator, config_entry))
    
    # Create per-assignee lists if enabled
    if config_entry.data.get(CONF_CREATE_ASSIGNEE_LISTS, True):
        _LOGGER.debug("Assignee lists enabled in config")
        _LOGGER.debug("Coordinator data available: %s", coordinator.data is not None)
        if coordinator.data:
            _LOGGER.debug("Number of tasks in coordinator: %d", len(coordinator.data))
            assignees = _get_unique_assignees(coordinator.data)
            _LOGGER.debug("Found assignees: %s", assignees)
            for assignee in assignees:
                # Use a simple hash of assignee name as ID since we don't have user IDs
                assignee_id = str(abs(hash(assignee)) % 10000)  # Simple numeric ID
                _LOGGER.debug("Creating entity for assignee: %s with ID: %s", assignee, assignee_id)
                entities.append(DonetickAssigneeTasksList(coordinator, config_entry, assignee, assignee_id))
        else:
            _LOGGER.warning("No coordinator data available for assignee entity creation")
    else:
        _LOGGER.debug("Assignee lists not enabled in config")
    
    _LOGGER.debug("Creating %d total entities", len(entities))
    async_add_entities(entities)

def _get_unique_assignees(tasks):
    """Get unique assignees from tasks."""
    if not tasks:
        _LOGGER.debug("No tasks found for assignee detection")
        return []
    
    _LOGGER.debug("Processing %d tasks for assignee detection", len(tasks))
    assignees = set()
    for task in tasks:
        _LOGGER.debug("Task: %s, assigned_to: %s, is_active: %s", task.name, task.assigned_to, task.is_active)
        if task.assigned_to and task.is_active:
            assignees.add(task.assigned_to)
    
    result = sorted(list(assignees))
    _LOGGER.debug("Unique assignees found: %s", result)
    return result

class DonetickTodoListBase(CoordinatorEntity, TodoListEntity):
    """Base class for Donetick Todo List entities."""
    
    _attr_supported_features = (
        TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the Todo List."""
        super().__init__(coordinator)
        self._config_entry = config_entry

    def _filter_tasks(self, tasks):
        """Filter tasks based on entity type. Override in subclasses."""
        return tasks

    @property
    def todo_items(self) -> list[TodoItem] | None: 
        """Return a list of todo items."""
        if self.coordinator.data is None:
            return None
        
        filtered_tasks = self._filter_tasks(self.coordinator.data)
        return [
            TodoItem(
                summary=task.name,
                uid="%s--%s" % (task.id, task.next_due_date),
                status=self.get_status(task.next_due_date, task.is_active),
                due=task.next_due_date,
                description=f"{self._config_entry.data[CONF_URL]}/chores/{task.id}"
            ) for task in filtered_tasks if task.is_active
        ]

    def get_status(self, due_date: datetime, is_active: bool) -> TodoItemStatus:
        """Return the status of the task."""
        if not is_active:
            return TodoItemStatus.COMPLETED
        return TodoItemStatus.NEEDS_ACTION

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a todo item."""
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
                res = await client.async_complete_task(item.uid.split("--")[0])
                if res.frequency_type != "once":
                    _LOGGER.debug("Task %s is recurring, updating next due date", res.name)
                    item.status = TodoItemStatus.NEEDS_ACTION
                    item.due = res.next_due_date
                    self.async_update_todo_item(item)
            except Exception as e:
                _LOGGER.error("Error completing task from Donetick: %s", e)
        
        await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        await self.coordinator.async_refresh()

class DonetickAllTasksList(DonetickTodoListBase):
    """Donetick All Tasks List entity."""

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the All Tasks List."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"dt_{config_entry.entry_id}_all_tasks"
        self._attr_name = "All Tasks"

    def _filter_tasks(self, tasks):
        """Return all active tasks."""
        return [task for task in tasks if task.is_active]

class DonetickAssigneeTasksList(DonetickTodoListBase):
    """Donetick Assignee-specific Tasks List entity."""

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry, assignee: str, assignee_id: str) -> None:
        """Initialize the Assignee Tasks List."""
        super().__init__(coordinator, config_entry)
        self._assignee = assignee
        self._assignee_id = assignee_id
        self._attr_unique_id = f"dt_{config_entry.entry_id}_{assignee_id}_tasks"
        self._attr_name = f"{assignee}'s Tasks"

    def _filter_tasks(self, tasks):
        """Return tasks assigned to this assignee."""
        return [task for task in tasks if task.is_active and task.assigned_to == self._assignee]

# Keep the old class for backward compatibility
class DonetickTodoListEntity(DonetickAllTasksList):
    """Donetick Todo List entity."""
    
    """Legacy Donetick Todo List entity for backward compatibility."""
    
    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the Todo List."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"dt_{config_entry.entry_id}"

