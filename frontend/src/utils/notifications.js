let notificationHandler = null

export const setNotificationHandler = (handler) => {
  notificationHandler = handler
}

export const showNotification = (message, type = 'info') => {
  if (notificationHandler) {
    notificationHandler(message, type)
  } else {
    console.log(`[${type.toUpperCase()}] ${message}`)
  }
}
