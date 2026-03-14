/**
 * AI Planner Service - Calls Firebase Cloud Function for Gemini itinerary generation
 * Requires Firebase to be initialized (call initFirebase() in _app.js).
 */

import { getFunctions, httpsCallable } from 'firebase/functions';
import { getApp } from 'firebase/app';

/**
 * Fetch a trip plan from the Gemini-powered Cloud Function.
 * @param {string[]|string} interests - Array of interest tags or comma-separated string
 * @param {number} days - Number of days for the trip
 * @param {string} location - Destination (e.g. "Tokyo, Japan")
 * @returns {Promise<{ text: string }>} - Result with text containing JSON itinerary
 */
export async function fetchTripPlan(interests, days, location) {
  let app;
  try {
    app = getApp();
  } catch {
    throw new Error('Firebase not initialized. Ensure initFirebase() is called and Firebase config is set.');
  }
  const functions = getFunctions(app);

  const generateItinerary = httpsCallable(functions, 'generateItinerary');

  const interestsArr = Array.isArray(interests)
    ? interests
    : typeof interests === 'string'
      ? interests.split(',').map((s) => s.trim()).filter(Boolean)
      : [];

  const result = await generateItinerary({
    interests: interestsArr.length ? interestsArr : ['general sightseeing'],
    days: Number(days) || 3,
    location: String(location || '')
  });

  const data = result.data;

  if (!data || typeof data.text !== 'string') {
    throw new Error('Invalid response from generateItinerary');
  }

  return { text: data.text };
}
