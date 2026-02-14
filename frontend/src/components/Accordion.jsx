import { useState, useEffect } from 'react'
import './Accordion.css'

export default function Accordion({ 
  title, 
  icon, 
  children, 
  defaultOpen = false,
  className = '',
  badge,
  onToggle
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  useEffect(() => {
    setIsOpen(defaultOpen)
  }, [defaultOpen])

  const handleToggle = () => {
    const newState = !isOpen
    setIsOpen(newState)
    if (onToggle) {
      onToggle(newState)
    }
  }

  return (
    <div className={`accordion ${className} ${isOpen ? 'open' : ''}`}>
      <button 
        className="accordion-header"
        onClick={handleToggle}
        aria-expanded={isOpen}
      >
        <div className="accordion-header-content">
          <span className="accordion-title">{title}</span>
          {badge && <span className="accordion-badge">{badge}</span>}
        </div>
        <span className={`accordion-chevron ${isOpen ? 'open' : ''}`}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
      </button>
      <div className={`accordion-content ${isOpen ? 'open' : ''}`}>
        <div className="accordion-body">
          {children}
        </div>
      </div>
    </div>
  )
}
