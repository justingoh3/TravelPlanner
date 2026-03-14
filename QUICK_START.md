# Quick Start Guide

## Backend Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   - Create `.env` file with your `MAPS_API_KEY`
   - Make sure Distance Matrix API is enabled in Google Cloud Console

3. **Start the FastAPI server:**
   ```bash
   python main.py
   ```
   Server runs on `http://localhost:8000`

## Frontend Setup

1. **Navigate to frontend:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment:**
   ```bash
   cp .env.local.example .env.local
   ```
   Edit `.env.local` and add:
   ```
   NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
   ```

4. **Start development server:**
   ```bash
   npm run dev
   ```
   Frontend runs on `http://localhost:3000`

## Usage

1. Open `http://localhost:3000` in your browser
2. Fill in the form:
   - Hotel address (e.g., "Shibuya, Tokyo, Japan")
   - Arrival date/time
   - Number of days
   - Wishlist items (comma-separated)
3. Click "Generate Itinerary"
4. View the interactive map and timeline!

## Testing the Backend Directly

You can test the API with curl:

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "hotel_address": "Shibuya, Tokyo, Japan",
    "arrival_time": "2024-03-15T14:00:00",
    "days": 3,
    "wishlist_items": ["Senso-ji Temple", "Tokyo Skytree"]
  }'
```

