# Tokyo Travel Planner - Frontend

Next.js frontend for the Tokyo Travel Planner application.

## Setup

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment:**
   ```bash
   cp .env.local.example .env.local
   ```
   Then edit `.env.local` and add your Google Maps API key:
   ```
   NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
   ```

3. **Run the development server:**
   ```bash
   npm run dev
   ```

   The app will be available at http://localhost:3000

## Features

- **Interactive Map**: Shows all locations for the selected day with polylines connecting them
- **Timeline Sidebar**: Clean vertical timeline with icons for different event types
- **Tabelog Badges**: Gold pill badges showing restaurant ratings
- **Google Maps Deep Links**: "Open in Maps" buttons for each transport segment
- **Day Navigation**: Switch between days to see different itineraries

## API Integration

The frontend connects to the FastAPI backend running on `http://localhost:8000`.

Make sure the backend is running before using the frontend:
```bash
# In the project root
python main.py
```

