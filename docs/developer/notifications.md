# Apollos AI Notifications

Quick guide for using the notification system in Apollos AI.

> [!TIP]
> Notifications pair well with scheduled tasks. See [Tasks & Scheduling](../guides/usage.md#tasks--scheduling) for automation patterns.

## Backend Usage

Use `NotificationManager` to send notifications from anywhere in your Python code:

```python
from python.helpers.notification import NotificationManager, NotificationType, NotificationPriority

# Basic notifications
NotificationManager.send_notification(
    type=NotificationType.INFO,
    priority=NotificationPriority.NORMAL,
    message="Operation completed",
)

NotificationManager.send_notification(
    type=NotificationType.SUCCESS,
    priority=NotificationPriority.NORMAL,
    message="File saved successfully",
    title="File Manager",
)

NotificationManager.send_notification(
    type=NotificationType.WARNING,
    priority=NotificationPriority.HIGH,
    message="High CPU usage detected",
    title="System Monitor",
)

NotificationManager.send_notification(
    type=NotificationType.ERROR,
    priority=NotificationPriority.HIGH,
    message="Connection failed",
    title="Network Error",
)

NotificationManager.send_notification(
    type=NotificationType.PROGRESS,
    priority=NotificationPriority.NORMAL,
    message="Processing files...",
    title="Task Progress",
)

# With details and custom display time
NotificationManager.send_notification(
    type=NotificationType.INFO,
    priority=NotificationPriority.NORMAL,
    message="System backup completed",
    title="Backup Manager",
    detail="<p>Backup size: <strong>2.4 GB</strong></p>",
    display_time=8,  # seconds
)

# Grouped notifications (replaces previous in same group)
NotificationManager.send_notification(
    type=NotificationType.PROGRESS,
    priority=NotificationPriority.NORMAL,
    message="Download: 25%",
    title="File Download",
    group="download-status",
)
NotificationManager.send_notification(
    type=NotificationType.PROGRESS,
    priority=NotificationPriority.NORMAL,
    message="Download: 75%",
    title="File Download",
    group="download-status",
)  # Replaces previous
NotificationManager.send_notification(
    type=NotificationType.SUCCESS,
    priority=NotificationPriority.NORMAL,
    message="Download complete!",
    title="File Download",
    group="download-status",
)  # Replaces previous
```

### API Reference

The `NotificationManager.send_notification()` static method accepts:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | `NotificationType` | Yes | — | `INFO`, `SUCCESS`, `WARNING`, `ERROR`, or `PROGRESS` |
| `priority` | `NotificationPriority` | Yes | — | `NORMAL` or `HIGH` |
| `message` | `str` | Yes | — | Main notification text |
| `title` | `str` | No | `""` | Notification title |
| `detail` | `str` | No | `""` | HTML content for expandable details |
| `display_time` | `int` | No | `3` | Toast display duration in seconds |
| `group` | `str` | No | `""` | Group identifier for replacement behavior |

### Notification API Endpoints

The backend also exposes REST endpoints for notification management:

| Endpoint | Description |
|----------|-------------|
| `notification_create` | Create a notification via API |
| `notifications_clear` | Clear all notifications |
| `notifications_history` | Get notification history |
| `notifications_mark_read` | Mark notifications as read |

### Agent Tool

Agents can send notifications using the `notify_user` tool (`python/tools/notify_user.py`), which triggers notifications visible to the user during agent execution.

## Frontend Usage

Use the notification store in Alpine.js components:

```javascript
// Basic notifications
$store.notificationStore.info("User logged in")
$store.notificationStore.success("Settings saved", "Configuration")
$store.notificationStore.warning("Session expiring soon")
$store.notificationStore.error("Failed to load data")
$store.notificationStore.progress("Processing...", "Task")

// With grouping
$store.notificationStore.info("Connecting...", "Status", "", 3, "connection")
$store.notificationStore.success("Connected!", "Status", "", 3, "connection")  // Replaces previous

// Frontend notifications with backend persistence
$store.notificationStore.frontendError("Database timeout", "Connection Error")
$store.notificationStore.frontendWarning("High memory usage", "Performance")
$store.notificationStore.frontendInfo("Cache cleared", "System")
$store.notificationStore.frontendSuccess("Upload complete", "Files")
$store.notificationStore.frontendProgress("Syncing data...", "Sync")
```

### Frontend Method Signatures

All notification methods accept:

```javascript
async info(message, title = "", detail = "", display_time = 3, group = "", priority = defaultPriority)
async success(message, title = "", detail = "", display_time = 3, group = "", priority = defaultPriority)
async warning(message, title = "", detail = "", display_time = 3, group = "", priority = defaultPriority)
async error(message, title = "", detail = "", display_time = 3, group = "", priority = defaultPriority)
async progress(message, title = "", detail = "", display_time = 3, group = "", priority = defaultPriority)
```

## Frontend Notifications with Backend Sync

Frontend notifications automatically sync to the backend when connected, providing persistent history and cross-session availability.

### How it Works:
- **Backend Connected**: Notifications are sent to backend and appear via polling (persistent)
- **Backend Disconnected**: Notifications show as frontend-only toasts (temporary)
- **Automatic Fallback**: Seamless degradation when backend is unavailable

### Global Functions:

```javascript
// These functions automatically try backend first, then fallback to frontend-only
toastFrontendError("Server unreachable", "Connection Error")
toastFrontendWarning("Slow connection detected")
toastFrontendInfo("Reconnected successfully")
toastFrontendSuccess("Upload complete")
toastFrontendProgress("Syncing data...")
```

## HTML Usage

```html
<button @click="$store.notificationStore.success('Task completed!')">
    Complete Task
</button>

<button @click="$store.notificationStore.warning('Progress: 50%', 'Upload', '', 5, 'upload-progress')">
    Update Progress
</button>

<!-- Frontend notifications with backend sync -->
<button @click="$store.notificationStore.frontendError('Connection failed', 'Network')">
    Report Connection Error
</button>
```

## Notification Groups

Groups ensure only the latest notification from each group is shown in the toast stack:

```python
# Progress updates - each new notification replaces the previous one
NotificationManager.send_notification(
    type=NotificationType.INFO,
    priority=NotificationPriority.NORMAL,
    message="Starting backup...",
    group="backup-status",
)
NotificationManager.send_notification(
    type=NotificationType.PROGRESS,
    priority=NotificationPriority.NORMAL,
    message="Backup: 80%",
    group="backup-status",
)  # Replaces previous
NotificationManager.send_notification(
    type=NotificationType.SUCCESS,
    priority=NotificationPriority.NORMAL,
    message="Backup complete!",
    group="backup-status",
)  # Replaces previous
```

## Types

- **info**: General information
- **success**: Successful operations
- **warning**: Important alerts
- **error**: Error conditions
- **progress**: Ongoing operations

## Behavior

- **Toast Display**: Notifications appear as toasts in the bottom-right corner
- **Persistent History**: All notifications (including synced frontend ones) are stored in notification history
- **Modal Access**: Full history accessible via the bell icon
- **Auto-dismiss**: Toasts automatically disappear after `display_time`
- **Group Replacement**: Notifications with the same group replace previous ones immediately
- **Backend Sync**: Frontend notifications automatically sync to backend when connected
- **Priority Levels**: `NORMAL` for routine messages, `HIGH` for urgent alerts
