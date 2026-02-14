import { useState, useCallback } from 'react'
import ToastNotification from './ToastNotification'
import './NotificationContainer.css'

let notificationId = 0
let notificationListeners = []

export function useNotifications() {
  const [notifications, setNotifications] = useState([])

  const showNotification = useCallback((message, type = 'info', duration = 5000) => {
    const id = notificationId++
    const notification = { id, message, type, duration, timestamp: Date.now() }
    
    setNotifications(prev => [...prev, notification])
    
    notificationListeners.forEach(listener => listener(notification))
    
    return id
  }, [])

  const removeNotification = useCallback((id) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  return { notifications, showNotification, removeNotification }
}

export default function NotificationContainer({ notifications, removeNotification }) {
  return (
    <div className="notification-container">
      {notifications.map(notification => (
        <ToastNotification
          key={notification.id}
          notification={notification}
          onClose={() => removeNotification(notification.id)}
        />
      ))}
    </div>
  )
}
