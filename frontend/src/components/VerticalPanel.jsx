import './VerticalPanel.css'

export default function VerticalPanel({ 
  children, 
  title, 
  icon,
  className = '',
  actions,
  collapsible = false,
  defaultCollapsed = false
}) {
  return (
    <div className={`vertical-panel ${className}`}>
      {(title || icon || actions) && (
        <div className="vertical-panel-header">
          <div className="vertical-panel-title-section">
            {title && <h3 className="vertical-panel-title">{title}</h3>}
          </div>
          {actions && (
            <div className="vertical-panel-actions">
              {actions}
            </div>
          )}
        </div>
      )}
      <div className="vertical-panel-content">
        {children}
      </div>
    </div>
  )
}
