# Zoria Frontend

React-based frontend for the Zoria learning platform.

## Features

- **Authentication**: Parent/Admin login, Child PIN login, Registration
- **Dashboard**: Overview, Children management, Document upload/viewing
- **Admin Panel**: Parent account management
- **Document Processing**: PDF upload with automatic concept extraction
- **Modern UI**: Clean, responsive design with smooth animations

## Tech Stack

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **React Markdown** - Markdown rendering for document content

## Getting Started

### Prerequisites

- Node.js 18+ and npm

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000` and will proxy API requests to `http://localhost:8000`.

### Build

```bash
npm run build
```

### Environment Variables

Create a `.env` file in the frontend directory:

```env
VITE_API_BASE=http://localhost:8000
```

## Project Structure

```
frontend/
├── src/
│   ├── components/      # Reusable UI components
│   │   ├── Accordion.jsx
│   │   ├── DocumentUpload.jsx
│   │   ├── DocumentList.jsx
│   │   ├── Header.jsx
│   │   ├── LoginForm.jsx
│   │   ├── RegisterForm.jsx
│   │   ├── ChildLoginForm.jsx
│   │   ├── CreateChild.jsx
│   │   └── ...
│   ├── pages/           # Page components
│   │   ├── Auth.jsx
│   │   ├── Dashboard.jsx
│   │   └── AdminSettings.jsx
│   ├── services/        # API client
│   │   └── api.js
│   ├── utils/           # Utilities
│   │   └── notifications.js
│   ├── styles/          # Global styles
│   │   └── index.css
│   ├── App.jsx          # Main app component
│   └── main.jsx         # Entry point
├── package.json
├── vite.config.js
└── index.html
```

## API Integration

The frontend communicates with the Zoria backend API at `/api/v1/*` endpoints:

- **Auth**: `/api/v1/auth/*`
- **Admin**: `/api/v1/admin/*`
- **Parent**: `/api/v1/parent/*`
- **Child**: `/api/v1/child/*`
- **Documents**: `/api/v1/documents/*`

See `src/services/api.js` for all API methods.

## Features by Role

### Parent/Admin
- Create and manage child profiles
- Upload documents for children
- View document list and processing status
- Admin: Create parent accounts

### Child
- View own profile
- Upload documents
- View uploaded documents

## Design System

The frontend uses a modern design system with CSS variables defined in `src/styles/index.css`:

- **Colors**: Primary (indigo), Secondary (purple), Success, Error, Warning
- **Spacing**: Consistent padding and margins
- **Typography**: System font stack with clear hierarchy
- **Components**: Reusable, accessible components

## Development Notes

- All API calls include JWT token authentication
- Session expiration is handled automatically
- Error notifications are shown via toast system
- Loading states are managed per component
