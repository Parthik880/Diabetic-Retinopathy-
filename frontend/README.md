# RetinaScan AI

An AI-assisted diabetic retinopathy screening and reporting tool. Clinicians can capture or upload retinal images, run AI-based analysis, compare scans over time, generate reports, and refer patients to specialists — all from a single interface.

## Features

- **Patient management** — add and switch between patient records
- **Image capture/upload** — capture or upload left (OS) and right (OD) eye retinal images
- **AI analysis** — automated grading of diabetic retinopathy severity using the Gemini API
- **Comparison view** — track changes in a patient's retinal scans across visits
- **Report generation** — produce a shareable clinical report
- **Specialist referral** — flag and refer cases that need specialist attention
- **Offline indicator** — UI reflects connectivity status

## Tech Stack

- **React 19** + **TypeScript**
- **Vite 6** — build tool and dev server
- **Express** — backend server (`server.ts`)
- **Tailwind CSS 4**
- **@google/genai** — Gemini API integration for AI-based analysis
- **lucide-react** — icons
- **motion** — animations

## Project Structure

```
├── src/
│   ├── components/        # UI screens and modals
│   │   ├── TopAppBar.tsx
│   │   ├── BottomNavBar.tsx
│   │   ├── CaptureScreen.tsx
│   │   ├── AnalysisScreen.tsx
│   │   ├── CompareScreen.tsx
│   │   ├── ReportScreen.tsx
│   │   ├── SpecialistReferralModal.tsx
│   │   ├── ImageUploadModal.tsx
│   │   └── AddPatientModal.tsx
│   ├── data/
│   │   └── samplePatients.ts   # sample/demo patient data
│   ├── types.ts            # shared TypeScript types
│   ├── App.tsx              # app shell and state management
│   ├── main.tsx             # React entry point
│   └── index.css
├── server.ts                # Express server entry point
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## Getting Started

**Prerequisites:** Node.js

1. Install dependencies:
   ```bash
   npm install
   ```
2. Configure environment variables — copy `.env.example` to `.env` and set your Gemini API key:
   ```bash
   cp .env.example .env
   ```
   Then set `GEMINI_API_KEY` in `.env`.
3. Run the app in development mode:
   ```bash
   npm run dev
   ```
4. Build for production:
   ```bash
   npm run build
   ```
5. Start the production build:
   ```bash
   npm start
   ```

## Available Scripts

| Script | Description |
|---|---|
| `npm run dev` | Start the dev server (`tsx server.ts`) |
| `npm run build` | Build the frontend (Vite) and bundle the server |
| `npm start` | Run the production server |
| `npm run clean` | Remove build output |
| `npm run lint` | Type-check with `tsc --noEmit` |

## Branch Structure

This branch (`frontend`) contains the RetinaScan AI web application. The diabetic retinopathy grading model (ConvNeXt + Grad-CAM) lives alongside it in this repo — see the `model/` directory for training scripts, inference code, and evaluation results.
