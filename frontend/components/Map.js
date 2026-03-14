import { useMemo, useEffect, useRef } from 'react'
import { APIProvider, Map as GoogleMap, Marker, useMap } from '@vis.gl/react-google-maps'

const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || ''

// Inner component that uses the map instance
function MapContent({ itinerary, hotelLocation, selectedDay, onGetRouteUrl }) {
  const map = useMap()
  const polylineRef = useRef(null)

  const { markers, polylines, waypoints, routeUrl } = useMemo(() => {
    if (!itinerary || !selectedDay || !itinerary[selectedDay]) {
      return { markers: [], polylines: [], waypoints: [] }
    }

    const events = itinerary[selectedDay]
    const points = []
    const waypointList = []

    // Add hotel location (not numbered, but included in route)
    if (hotelLocation) {
      points.push({
        lat: hotelLocation.latitude,
        lng: hotelLocation.longitude,
        label: 'Hotel',
        type: 'hotel',
        markerNumber: null // Hotel doesn't get a number
      })
    }

    // Add event locations with numbers (TASK 3: Numbered markers)
    let markerNumber = 1
    events.forEach((event, index) => {
      if (event.latitude && event.longitude) {
        // Only number non-transport events (sight, meal)
        const shouldNumber = event.type === 'sight' || event.type === 'meal'
        
        points.push({
          lat: event.latitude,
          lng: event.longitude,
          label: event.name,
          type: event.type,
          tabelog_score: event.tabelog_score,
          index,
          markerNumber: shouldNumber ? markerNumber++ : null
        })
        
        // Add to waypoints for Google Maps route (exclude transport-only events)
        if (shouldNumber) {
          waypointList.push(`${event.latitude},${event.longitude}`)
        }
      }
    })

    // Create polyline path
    const path = points.map(p => ({ lat: p.lat, lng: p.lng }))

    // TASK 4: Generate Google Maps route URL with waypoints
    // Format: origin=Hotel, destination=LastStop, waypoints=AllIntermediateStops
    let routeUrl = null
    if (hotelLocation && waypointList.length > 0) {
      const origin = `${hotelLocation.latitude},${hotelLocation.longitude}`
      const destination = waypointList[waypointList.length - 1] // Last stop is destination
      const waypointsParam = waypointList.length > 1 
        ? waypointList.slice(0, -1).join('|') // All but last as waypoints
        : '' // If only one waypoint, no intermediate waypoints needed
      
      if (waypointsParam) {
        routeUrl = `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&waypoints=${waypointsParam}&travelmode=transit`
      } else {
        // Single stop - no waypoints needed
        routeUrl = `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&travelmode=transit`
      }
    }

    return {
      markers: points,
      polylines: path.length > 1 ? path : [],
      waypoints: waypointList,
      routeUrl
    }
  }, [itinerary, selectedDay, hotelLocation])
  
  // Expose route URL to parent component
  useEffect(() => {
    if (onGetRouteUrl && routeUrl) {
      onGetRouteUrl(routeUrl)
    }
  }, [routeUrl, onGetRouteUrl])

  // Draw polyline using Google Maps API directly
  useEffect(() => {
    if (!map || !polylines || polylines.length < 2) {
      // Remove existing polyline if path is invalid
      if (polylineRef.current) {
        polylineRef.current.setMap(null)
        polylineRef.current = null
      }
      return
    }

    // Wait for Google Maps to be loaded
    if (!window.google || !window.google.maps) {
      return
    }

    // Remove existing polyline
    if (polylineRef.current) {
      polylineRef.current.setMap(null)
    }

    // Create new polyline using native Google Maps API
    const path = polylines.map(p => new window.google.maps.LatLng(p.lat, p.lng))
    
    polylineRef.current = new window.google.maps.Polyline({
      path: path,
      geodesic: true,
      strokeColor: '#3B82F6',
      strokeOpacity: 0.8,
      strokeWeight: 3,
      map: map
    })

    // Cleanup function
    return () => {
      if (polylineRef.current) {
        polylineRef.current.setMap(null)
        polylineRef.current = null
      }
    }
  }, [map, polylines])

  return (
    <>
      {/* Hotel Marker */}
      {hotelLocation && (
        <Marker
          position={{ lat: hotelLocation.latitude, lng: hotelLocation.longitude }}
          title="Hotel"
          icon={{
            url: 'http://maps.google.com/mapfiles/ms/icons/blue-dot.png'
          }}
        />
      )}

      {/* Event Markers with Numbers (TASK 3) */}
      {markers.map((point, index) => {
        // Determine icon based on type
        let iconUrl = 'http://maps.google.com/mapfiles/ms/icons/green-dot.png'
        if (point.type === 'hotel') {
          iconUrl = 'http://maps.google.com/mapfiles/ms/icons/blue-dot.png'
        } else if (point.type === 'meal') {
          iconUrl = 'http://maps.google.com/mapfiles/ms/icons/red-dot.png'
        }
        
        return (
          <Marker
            key={index}
            position={{ lat: point.lat, lng: point.lng }}
            title={point.label}
            icon={{
              url: iconUrl
            }}
            label={point.markerNumber !== null ? {
              text: String(point.markerNumber),
              color: '#FFFFFF',
              fontSize: '14px',
              fontWeight: 'bold'
            } : undefined}
          />
        )
      })}
    </>
  )
}

export function Map({ itinerary, hotelLocation, selectedDay, routeUrl, onRouteUrlChange }) {
  const { center, zoom } = useMemo(() => {
    if (!itinerary || !selectedDay || !itinerary[selectedDay]) {
      return {
        center: { lat: 35.6762, lng: 139.6503 }, // Tokyo center
        zoom: 12
      }
    }

    const events = itinerary[selectedDay]
    const points = []

    // Add hotel location
    if (hotelLocation) {
      points.push({
        lat: hotelLocation.latitude,
        lng: hotelLocation.longitude
      })
    }

    // Add event locations
    events.forEach((event) => {
      if (event.latitude && event.longitude) {
        points.push({
          lat: event.latitude,
          lng: event.longitude
        })
      }
    })

    // Calculate center
    if (points.length === 0) {
      return { center: { lat: 35.6762, lng: 139.6503 }, zoom: 12 }
    }

    const avgLat = points.reduce((sum, p) => sum + p.lat, 0) / points.length
    const avgLng = points.reduce((sum, p) => sum + p.lng, 0) / points.length

    return {
      center: { lat: avgLat, lng: avgLng },
      zoom: 13
    }
  }, [itinerary, selectedDay, hotelLocation])

  if (!API_KEY) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-100">
        <div className="text-center p-8">
          <p className="text-gray-600 mb-2">Google Maps API key not configured</p>
          <p className="text-sm text-gray-500">
            Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY in .env.local
          </p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', minHeight: '100vh' }}>
      <APIProvider 
        apiKey={API_KEY} 
        libraries={['places']}
        onLoad={() => console.log('Google Maps loaded')}
      >
        <GoogleMap
          defaultCenter={center}
          defaultZoom={zoom}
          mapId="tokyo-travel-planner"
          style={{ width: '100%', height: '100%', minHeight: '100vh' }}
        >
          <MapContent 
            itinerary={itinerary}
            hotelLocation={hotelLocation}
            selectedDay={selectedDay}
            onGetRouteUrl={onRouteUrlChange}
          />
        </GoogleMap>
        
        {/* TASK 4: Open Full Route Button */}
        {routeUrl && (
          <div className="absolute top-4 right-4 z-10">
            <a
              href={routeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md shadow-lg font-medium text-sm flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
              Open Full Route in Google Maps
            </a>
          </div>
        )}
      </APIProvider>
    </div>
  )
}
