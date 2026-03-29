import { useState, useEffect, useRef } from 'react'
import { MapPin, Coffee, Train, Plane, Clock, GripVertical } from 'lucide-react'
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd'

export function Timeline({ itinerary, setItinerary, hotelLocation, selectedDay, onDaySelect, onGenerate, loading, error }) {
  const INTEREST_OPTIONS = [
    { value: 'temples_shrines', label: 'Temples & Shrines' },
    { value: 'anime_manga', label: 'Anime & Manga' },
    { value: 'nature_parks', label: 'Nature & Parks' },
    { value: 'shopping', label: 'General Shopping' },
    { value: 'clothes_shopping', label: 'Clothes Shopping' },
    { value: 'cafe_hopping', label: 'Cafe Hopping' },
    { value: 'foodie', label: 'Foodie' },
    { value: 'history', label: 'History' }
  ]

  const [formData, setFormData] = useState({
    hotel_address: 'Shibuya, Tokyo, Japan',
    arrival_time: new Date().toISOString().slice(0, 16),
    departure_flight_time: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16), // Default to 3 days later
    wishlist_items: 'Senso-ji Temple, Tokyo Skytree, Shibuya Crossing, Meiji Shrine, Tsukiji Outer Market',
    interests: []
  })

  


  const recalculateItinerary = async (updatedItinerary) => {
    try {
      const response = await fetch('http://localhost:8000/api/recalculate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          hotel_address: formData.hotel_address,
          arrival_time: new Date(formData.arrival_time).toISOString(),
          itinerary: updatedItinerary
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

  const handleMoveDay = (event, sourceDay, destDay, index) => {
    if (sourceDay === destDay) return;
    const newItinerary = { ...itinerary };
    const sourceEvents = Array.from(newItinerary[sourceDay]);
    const destEvents = Array.from(newItinerary[destDay] || []);
    
    // Remove from source
    const [movedItem] = sourceEvents.splice(index, 1);
    
    // Add to dest
    destEvents.push(movedItem);
    
    newItinerary[sourceDay] = sourceEvents;
    newItinerary[destDay] = destEvents;
    setItinerary(newItinerary);
    recalculateItinerary(newItinerary);
  };

  const handleDragEnd = (result) => {
    if (!result.destination) return;
    
    const sourceIndex = result.source.index;
    const destIndex = result.destination.index;
    
    if (sourceIndex === destIndex) return;
    
    const newItinerary = { ...itinerary };
    const dayEvents = Array.from(newItinerary[selectedDay]);
    
    // Reorder
    const [removed] = dayEvents.splice(sourceIndex, 1);
    dayEvents.splice(destIndex, 0, removed);
    
    newItinerary[selectedDay] = dayEvents;
    setItinerary(newItinerary);
    recalculateItinerary(newItinerary);
  };

  const toggleInterest = (value) => {
    setFormData(prev => ({
      ...prev,
      interests: prev.interests.includes(value)
        ? prev.interests.filter(i => i !== value)
        : [...prev.interests, value]
    }))
  }
  
  const autocompleteRef = useRef(null)
  const autocompleteInputRef = useRef(null)

  // Initialize Google Places Autocomplete
  useEffect(() => {
    const initAutocomplete = () => {
      if (autocompleteInputRef.current && !autocompleteRef.current && 
          window.google && window.google.maps && window.google.maps.places) {
        try {
          autocompleteRef.current = new window.google.maps.places.Autocomplete(
            autocompleteInputRef.current,
            {
              types: ['establishment', 'geocode'],
              componentRestrictions: { country: 'jp' },
              fields: ['formatted_address', 'geometry', 'name']
            }
          )
          
          autocompleteRef.current.addListener('place_changed', () => {
            const place = autocompleteRef.current.getPlace()
            if (place && place.formatted_address) {
              setFormData(prev => ({...prev, hotel_address: place.formatted_address}))
            }
          })
        } catch (error) {
          console.error('Error initializing autocomplete:', error)
        }
      }
    }

    if (typeof window !== 'undefined') {
      if (window.google && window.google.maps && window.google.maps.places) {
        // Google Maps already loaded
        initAutocomplete()
      } else {
        // Wait for Google Maps to load (from _app.js Script tag)
        let attempts = 0
        const maxAttempts = 50 // 5 seconds max wait
        
        const checkGoogle = setInterval(() => {
          attempts++
          if (window.google && window.google.maps && window.google.maps.places) {
            clearInterval(checkGoogle)
            initAutocomplete()
          } else if (attempts >= maxAttempts) {
            clearInterval(checkGoogle)
            console.warn('Google Maps Places library not loaded after timeout')
          }
        }, 100)
        
        return () => clearInterval(checkGoogle)
      }
    }
  }, [])

  const handleSubmit = (e) => {
    e.preventDefault()
    const wishlist = formData.wishlist_items.split(',').map(item => item.trim()).filter(Boolean)
    const requestData = {
      hotel_address: formData.hotel_address,
      arrival_time: new Date(formData.arrival_time).toISOString(),
      departure_flight_time: new Date(formData.departure_flight_time).toISOString(), // Required
      wishlist_items: wishlist,
      interests: formData.interests || []
    }
    
    onGenerate(requestData)
  }

  const getIcon = (type) => {
    switch (type) {
      case 'arrival':
        return <Plane className="w-5 h-5 text-blue-500" />
      case 'sight':
        return <MapPin className="w-5 h-5 text-green-500" />
      case 'meal':
        return <Coffee className="w-5 h-5 text-orange-500" />
      default:
        return <MapPin className="w-5 h-5 text-gray-500" />
    }
  }

  const getGoogleMapsLink = (event, prevEvent) => {
    if (!event.latitude || !event.longitude) return null
    if (!prevEvent || !prevEvent.latitude || !prevEvent.longitude) return null
    
    const origin = `${prevEvent.latitude},${prevEvent.longitude}`
    const destination = `${event.latitude},${event.longitude}`
    return `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&travelmode=transit`
  }

  if (!itinerary) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Tokyo Travel Planner</h1>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Hotel Address <span className="text-red-500">*</span>
            </label>
            <input
              ref={autocompleteInputRef}
              type="text"
              value={formData.hotel_address}
              onChange={(e) => setFormData({...formData, hotel_address: e.target.value})}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Start typing hotel address..."
              required
            />
            <p className="mt-1 text-xs text-gray-500">Autocomplete enabled - start typing to see suggestions</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Arrival Time <span className="text-red-500">*</span>
            </label>
            <input
              type="datetime-local"
              value={formData.arrival_time}
              onChange={(e) => setFormData({...formData, arrival_time: e.target.value})}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Departure Flight Time <span className="text-red-500">*</span>
            </label>
            <input
              type="datetime-local"
              value={formData.departure_flight_time}
              onChange={(e) => setFormData({...formData, departure_flight_time: e.target.value})}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              required
            />
            <p className="mt-1 text-xs text-gray-500">Number of days will be calculated automatically from arrival and departure times</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Your Interests
            </label>
            <div className="flex flex-wrap gap-2">
              {INTEREST_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleInterest(value)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    formData.interests.includes(value)
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500">We&apos;ll recommend places that match your interests</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Wishlist Items (comma-separated)
            </label>
            <textarea
              value={formData.wishlist_items}
              onChange={(e) => setFormData({...formData, wishlist_items: e.target.value})}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows="4"
              placeholder="Senso-ji Temple, Tokyo Skytree, Shibuya Crossing..."
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Generating...' : 'Generate Itinerary'}
          </button>
        </form>

        {error && (
          <div className="mt-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="p-4">
      <h1 className="text-xl font-bold mb-4">Itinerary Timeline</h1>
      
      {/* Day Selector */}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {Object.keys(itinerary).map((day) => (
          <button
            key={day}
            onClick={() => onDaySelect(day)}
            className={`px-3 py-1 rounded-md text-sm whitespace-nowrap ${
              selectedDay === day
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            {day}
          </button>
        ))}
      </div>

      {/* Timeline for Selected Day */}
      {selectedDay && itinerary[selectedDay] && (
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId={selectedDay}>
            {(provided) => (
              <div
                {...provided.droppableProps}
                ref={provided.innerRef}
                className="space-y-3"
              >
                {itinerary[selectedDay].map((event, index) => {
            const prevEvent = index > 0 ? itinerary[selectedDay][index - 1] : null
            const mapsLink = getGoogleMapsLink(event, prevEvent || (hotelLocation && {
              latitude: hotelLocation.latitude,
              longitude: hotelLocation.longitude
            }))

            return (
              <Draggable key={`${event.name}-${index}`} draggableId={`${event.name}-${index}`} index={index}>
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.draggableProps}
                    className={`border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow bg-white ${snapshot.isDragging ? 'shadow-lg ring-2 ring-blue-500' : ''}`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        {...provided.dragHandleProps}
                        className="mt-1 cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600"
                      >
                        <GripVertical className="w-5 h-5" />
                      </div>
                      <div className="mt-1">{getIcon(event.type)}</div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4 text-gray-500" />
                      <span className="text-sm font-medium text-gray-700">{event.time}</span>
                    </div>
                    <div className="flex items-center gap-2 justify-between">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900">{event.name}</h3>
                        {event.is_recommendation && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                            ✨ Suggested
                          </span>
                        )}
                      </div>
                      <select 
                        className="text-xs border-gray-300 rounded p-1"
                        value={selectedDay}
                        onChange={(e) => handleMoveDay(event, selectedDay, e.target.value, index)}
                      >
                        {Object.keys(itinerary).map(day => (
                          <option key={day} value={day}>Move to {day}</option>
                        ))}
                      </select>
                    </div>
                    
                    {event.type === 'meal' && event.tabelog_score && (
                      <div className="mt-1">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                          ⭐ {event.tabelog_score} Tabelog
                        </span>
                        {event.genre && (
                          <span className="ml-2 text-xs text-gray-500">{event.genre}</span>
                        )}
                      </div>
                    )}
                    
                    {event.is_recommendation && event.rating && (
                      <div className="mt-1">
                        <span className="text-xs text-gray-600">
                          ⭐ {event.rating.toFixed(1)} rating • {event.user_ratings_total?.toLocaleString() || 0} reviews
                        </span>
                      </div>
                    )}

                    {event.travel_text && (
                      <div className="mt-2 p-2 bg-blue-50 rounded-md">
                        <div className="flex items-center gap-2">
                          <Train className="w-4 h-4 text-blue-600" />
                          <span className="text-sm font-medium text-blue-900">Travel Time:</span>
                          <span className="text-sm text-blue-700">{event.travel_text}</span>
                          {mapsLink && (
                            <a
                              href={mapsLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ml-auto text-xs text-blue-600 hover:underline font-medium"
                            >
                              Open in Maps →
                            </a>
                          )}
                        </div>
                        {event.travel_mode && event.travel_mode === 'transit' && (
                          <p className="mt-1 text-xs text-blue-600">Using public transit</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                  </div>
                )}
              </Draggable>
            )
          })}
          {provided.placeholder}
        </div>
        )}
        </Droppable>
      </DragDropContext>
      )}
    </div>
  )
}

