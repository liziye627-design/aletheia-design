# Frontend Runtime Guide

## Current Runtime Mainline
- Active UI entry switcher: `frontend/src/entry.ts`
- New React runtime (default): `frontend/src/main.tsx` + `frontend/src/App.tsx`
- Legacy runtime (fallback): `frontend/src/main.js` + `frontend/src/styles.css`

Default behavior enables the new React UI. To force legacy mode:

```bash
VITE_NEW_PROGRAM_UI=0 npm run dev
```

## Local Run
```bash
cd frontend
npm install
npm run dev
```

Default frontend URL: `http://localhost:5173`

## Build
```bash
cd frontend
npm run build
```

## Unit Tests
```bash
cd frontend
npm run test:unit
```

## E2E (optional)
```bash
cd frontend
npm run test:e2e
```
