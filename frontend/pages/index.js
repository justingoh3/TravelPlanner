import { useState } from 'react'
import dynamic from 'next/dynamic'

// Dynamically import Map to avoid SSR issues
const Map = dynamic(() => import('../components/Map').then(mod => ({ default: mod.Map })), {
  ssr: false
})

import { Timeline } from '../components/Timeline'

const CalendarGrid = dynamic(() => import('../components/CalendarGrid').then(mod => ({ default: mod.CalendarGrid })), {
  ssr: false
})


export default function Home() {
  const [itinerary, setItinerary] = useState(null)
  const [hotelLocation, setHotelLocation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedDay, setSelectedDay] = useState(null)
  const [routeUrl, setRouteUrl] = useState(null)
  const [viewMode, setViewMode] = useState('list') // 'list' or 'calendar'
  const [lastRequestData, setLastRequestData] = useState(null)

  const handleExportICS = async () => {
    if (!lastRequestData || !itinerary) return;
    try {
      const response = await fetch('http://localhost:8000/api/export', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          hotel_address: lastRequestData.hotel_address,
          arrival_time: new Date(lastRequestData.arrival_time).toISOString(),
          itinerary: itinerary
        }),
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'tokyo_itinerary.ics';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error("Failed to export ICS", err);
    }
  };

  const handleSwap = async (dayKey, index) => {
    if (!lastRequestData) return;
    try {
      const response = await fetch('http://localhost:8000/api/swap', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          hotel_address: lastRequestData.hotel_address,
          arrival_time: new Date(lastRequestData.arrival_time).toISOString(),
          itinerary: itinerary,
          day_key: dayKey,
          item_index: index,
          pacing: lastRequestData.pacing
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setItinerary(data.itinerary);
      }
    } catch (err) {
      console.error("Failed to swap", err);
    }
  };

  const handleRecalculate = async (updatedItinerary) => {
    if (!lastRequestData) return;
    try {
      const response = await fetch('http://localhost:8000/api/recalculate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          hotel_address: lastRequestData.hotel_address,
          arrival_time: new Date(lastRequestData.arrival_time).toISOString(),
          itinerary: updatedItinerary,
          pacing: lastRequestData.pacing
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setItinerary(data.itinerary);
      }
    } catch (err) {
      console.error("Failed to recalculate", err);
    }
  };

  const handleGenerate = async (formData) => {
    setLastRequestData(formData)
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetch('http://localhost:8000/api/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to generate itinerary')
      }

      const data = await response.json()
      setItinerary(data.itinerary)
      setHotelLocation(data.hotel_location)
      // Select first day by default
      const firstDay = Object.keys(data.itinerary)[0]
      setSelectedDay(firstDay)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen">
            {/* Left Sidebar - Timeline */}
      <div className="w-96 bg-white border-r border-gray-200 overflow-y-auto flex flex-col">
        {itinerary && (
          <div className="flex border-b border-gray-200">
            <button 
              className={`flex-1 py-2 text-sm font-medium ${viewMode === 'list' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setViewMode('list')}
            >
              List View
            </button>
            <button 
              className={`flex-1 py-2 text-sm font-medium ${viewMode === 'calendar' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setViewMode('calendar')}
            >
              Calendar
            </button>
            <button 
              className={`flex-1 py-2 text-sm font-medium text-purple-600 hover:bg-purple-50 transition-colors`}
              onClick={handleExportICS}
              title="Export to Apple/Google Calendar"
            >
              📅 Export
            </button>
          </div>
        )}
        {(!itinerary || viewMode === 'list') ? (
          <Timeline
            itinerary={itinerary}
            setItinerary={setItinerary}
            hotelLocation={hotelLocation}
            selectedDay={selectedDay}
            onDaySelect={setSelectedDay}
            onGenerate={handleGenerate}
            loading={loading}
            error={error}
            onSwap={handleSwap}
          />
        ) : (
          <CalendarGrid 
            itinerary={itinerary} 
            setItinerary={setItinerary}
            arrivalTime={lastRequestData ? new Date(lastRequestData.arrival_time).toISOString() : null}
            onRecalculate={handleRecalculate}
          />
        )}
      </div>

      {/* Right Side - Map */}
      <div className="flex-1 relative" style={{ minHeight: '100vh' }}>
        <Map
          itinerary={itinerary}
          hotelLocation={hotelLocation}
          selectedDay={selectedDay}
          routeUrl={routeUrl}
          onRouteUrlChange={setRouteUrl}
        />
      </div>
    </div>
  )
}

