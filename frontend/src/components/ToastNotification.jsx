import { useState, useEffect } from 'react'
import './ToastNotification.css'

export default function ToastNotification({ notification, onClose }) {
  const [isVisible, setIsVisible] = useState(false)
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    setTimeout(() => setIsVisible(true), 10)
    
    const duration = notification.type === 'error' 
      ? (notification.duration || 30000)
      : (notification.duration || 5000)
    
    const timer = setTimeout(() => {
      handleClose()
    }, duration)

    return () => clearTimeout(timer)
  }, [])

  const handleClose = () => {
    setIsExiting(true)
    setTimeout(() => {
      onClose()
    }, 300)
  }

  const getIcon = () => {
    switch (notification.type) {
      case 'success':
        return '✓'
      case 'error':
        return '✕'
      case 'warning':
        return '⚠'
      default:
        return 'ℹ'
    }
  }

  return (
    <div
      className={`toast toast-${notification.type} ${isVisible ? 'toast-visible' : ''} ${isExiting ? 'toast-exiting' : ''} ${notification.type === 'error' ? 'toast-error-persistent' : ''}`}
      onClick={notification.type === 'error' ? undefined : handleClose}
    >
      <div className="toast-icon">{getIcon()}</div>
      <div className="toast-content">
        <div className="toast-message">{notification.message}</div>
      </div>
      <button className="toast-close" onClick={handleClose} aria-label="Close">
        ×
      </button>
    </div>
  )
}
