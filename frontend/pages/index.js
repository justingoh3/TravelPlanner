import { useState } from 'react'
import dynamic from 'next/dynamic'

// Dynamically import Map to avoid SSR issues
const Map = dynamic(() => import('../components/Map').then(mod => ({ default: mod.Map })), {
  ssr: false
})

import { Timeline } from '../components/Timeline'

export default function Home() {
  const [itinerary, setItinerary] = useState(null)
  const [hotelLocation, setHotelLocation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedDay, setSelectedDay] = useState(null)
  const [routeUrl, setRouteUrl] = useState(null)

  const handleGenerate = async (formData) => {
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
      <div className="w-96 bg-white border-r border-gray-200 overflow-y-auto">
        <Timeline
          itinerary={itinerary}
          setItinerary={setItinerary}
          hotelLocation={hotelLocation}
          selectedDay={selectedDay}
          onDaySelect={setSelectedDay}
          onGenerate={handleGenerate}
          loading={loading}
          error={error}
        />
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

