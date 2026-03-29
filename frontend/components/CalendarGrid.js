import { useRef, useEffect, useState } from 'react'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'

export function CalendarGrid({ itinerary, setItinerary, arrivalTime, onRecalculate }) {
  const [events, setEvents] = useState([])
  
  useEffect(() => {
    if (!itinerary) return;
    
    // Convert itinerary dictionary to FullCalendar events
    const newEvents = []
    
    // We need a base date. Let's parse arrivalTime or use today.
    const baseDate = arrivalTime ? new Date(arrivalTime) : new Date();
    baseDate.setHours(0,0,0,0);
    
    Object.keys(itinerary).forEach((dayKey) => {
      const dayNum = parseInt(dayKey.replace("Day ", "")) || 1;
      const dayEvents = itinerary[dayKey];
      
      const eventDate = new Date(baseDate.getTime() + (dayNum - 1) * 24 * 60 * 60 * 1000);
      const dateString = eventDate.toISOString().split('T')[0];
      
      dayEvents.forEach((item, index) => {
        if (!item.time) return;
        
        // Parse time (HH:MM)
        const [hours, minutes] = item.time.split(':').map(Number);
        
        const start = new Date(eventDate);
        start.setHours(hours, minutes, 0, 0);
        
        // Duration
        const durationHours = item.duration_hours || (item.type === 'meal' ? 1.0 : 1.5);
        const end = new Date(start.getTime() + durationHours * 60 * 60 * 1000);
        
        let color = '#3b82f6'; // blue (sight)
        if (item.type === 'meal') color = '#f97316'; // orange
        if (item.type === 'arrival') color = '#10b981'; // green
        if (item.is_closed_warning) color = '#ef4444'; // red for warning
        
        newEvents.push({
          id: `${dayKey}-${index}`,
          title: item.name + (item.is_closed_warning ? ' (CLOSED)' : ''),
          start: start.toISOString(),
          end: end.toISOString(),
          backgroundColor: color,
          borderColor: color,
          extendedProps: {
            dayKey,
            index,
            originalItem: item
          }
        });
      });
    });
    
    setEvents(newEvents);
  }, [itinerary, arrivalTime]);

  const handleEventChange = (changeInfo) => {
    // This runs when an event is dragged (resized or dropped to new time)
    const { event } = changeInfo;
    const { dayKey, index, originalItem } = event.extendedProps;
    
    const start = event.start;
    const end = event.end;
    
    // Calculate new duration in hours
    const durationMs = end.getTime() - start.getTime();
    const durationHours = durationMs / (1000 * 60 * 60);
    
    // Create new itinerary to mutate
    const newItinerary = { ...itinerary };
    
    // Update the duration on the specific event
    newItinerary[dayKey][index].duration_hours = durationHours;
    
    // Update local state temporarily to feel snappy
    setItinerary(newItinerary);
    
    // Trigger recalculation on backend
    if (onRecalculate) {
        onRecalculate(newItinerary);
    }
  };

  if (!itinerary) return null;

  return (
    <div className="p-4 h-full bg-white overflow-auto">
      <h2 className="text-xl font-bold mb-4">Calendar View</h2>
      <div className="text-xs mb-4 text-gray-500">
        Drag the bottom of an event to extend its duration. The system will automatically recalculate transit times and check opening hours!
      </div>
      <FullCalendar
        plugins={[ timeGridPlugin, interactionPlugin ]}
        initialView="timeGridDay"
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'timeGridDay,timeGridWeek'
        }}
        events={events}
        editable={true}
        droppable={false} // We handle ordering via the other view or custom logic
        eventResize={handleEventChange}
        eventDrop={handleEventChange}
        height="auto"
        slotMinTime="08:00:00"
        slotMaxTime="22:00:00"
        allDaySlot={false}
        initialDate={arrivalTime ? new Date(arrivalTime).toISOString().split('T')[0] : new Date().toISOString().split('T')[0]}
      />
    </div>
  )
}
