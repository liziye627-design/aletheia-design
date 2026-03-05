# Aletheia Mobile - Truth Engine Mobile App

A React Native mobile application for the Aletheia truth verification platform.

## Tech Stack

- **React Native** with **Expo SDK 50**
- **TypeScript** for type safety
- **React Navigation 6** for navigation
- **Zustand** for state management
- **Axios** for API calls
- **Expo SecureStore** for secure token storage

## Project Structure

```
aletheia-mobile/
├── App.tsx                    # App entry point
├── src/
│   ├── components/            # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Card.tsx
│   │   ├── CredibilityBadge.tsx
│   │   └── FeedCard.tsx
│   ├── screens/               # Screen components
│   │   ├── LoginScreen.tsx
│   │   ├── FeedsScreen.tsx
│   │   ├── AuditScreen.tsx
│   │   ├── ReportsScreen.tsx
│   │   └── ProfileScreen.tsx
│   ├── navigation/            # Navigation configuration
│   │   └── AppNavigator.tsx
│   ├── services/              # API services
│   │   ├── api.ts             # Axios client
│   │   ├── config.ts          # API configuration
│   │   ├── auth.ts            # Authentication
│   │   ├── intel.ts           # Intelligence analysis
│   │   ├── feeds.ts           # Feeds data
│   │   └── reports.ts         # Reports
│   ├── store/                 # Zustand stores
│   │   ├── authStore.ts
│   │   └── feedsStore.ts
│   ├── types/                 # TypeScript types
│   │   └── index.ts
│   └── utils/                 # Utilities
│       └── theme.ts           # Design system
├── assets/                    # Static assets
├── app.json                   # Expo config
├── package.json
├── tsconfig.json
└── babel.config.js
```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Expo CLI
- iOS Simulator (macOS) or Android Emulator

### Installation

```bash
# Navigate to the mobile app directory
cd aletheia-mobile

# Install dependencies
npm install

# Start the development server
npm start
```

### Running on Device/Emulator

```bash
# iOS (requires macOS)
npm run ios

# Android
npm run android

# Web
npm run web
```

## Backend Integration

The mobile app connects to the Aletheia Backend API. Configure the API endpoint in:

```typescript
// src/services/config.ts
const API_BASE_URL = __DEV__ 
  ? 'http://localhost:8000'  // Development - local backend
  : 'https://api.aletheia.app';  // Production
```

### Running with Local Backend

1. Start the backend server:
```bash
cd ../aletheia-backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. For Android emulator, use `10.0.2.2` instead of `localhost`:
```typescript
const API_BASE_URL = __DEV__ 
  ? Platform.OS === 'android' 
    ? 'http://10.0.2.2:8000'
    : 'http://localhost:8000'
  : 'https://api.aletheia.app';
```

## Features

### Login Screen
- WeChat one-click login
- Email/password login
- Dark theme matching design spec

### Discover (Feeds)
- Real-time news feed
- Credibility score badges
- Risk tag indicators
- Pull-to-refresh

### Audit Workbench
- Content input for analysis
- Real-time credibility scoring
- Reasoning chain visualization
- Risk tag display

### Reports
- Generated report list
- Report detail view
- Create new reports

### Profile
- User information
- Statistics dashboard
- Settings

## Design System

Based on `aletheia-ui.pen` specifications:

- **Primary Color**: #2563EB (Blue)
- **Success/Brand**: #059669 (Emerald)
- **WeChat**: #07C160
- **Background**: #050505 (Dark)
- **Font**: Inter / Noto Sans CJK

## API Endpoints

The app integrates with these backend endpoints:

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/login` | User authentication |
| `POST /api/v1/intel/analyze` | Analyze content |
| `GET /api/v1/intel/trending` | Get trending topics |
| `GET /api/v1/feeds` | Get news feeds |
| `GET /api/v1/reports` | List reports |
| `POST /api/v1/reports/generate` | Generate report |

## Development

### Type Checking
```bash
npm run typecheck
```

### Linting
```bash
npm run lint
```

### Building for Production

```bash
# Build for iOS
eas build --platform ios

# Build for Android
eas build --platform android
```

## Project Status

- [x] Project setup
- [x] Theme and design system
- [x] API service layer
- [x] Authentication flow
- [x] Login screen
- [x] Feeds screen
- [x] Audit screen
- [x] Reports screen
- [x] Profile screen
- [x] Bottom navigation
- [ ] Detail screens (IntelDetail, ReportDetail)
- [ ] Search functionality
- [ ] Push notifications
- [ ] Offline support

## License

MIT License - Part of the Aletheia Project
