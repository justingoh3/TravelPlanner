/**
 * Firebase Cloud Functions - Gemini AI Itinerary Generator
 * Securely calls Google AI Studio API from the backend.
 */

const { onCall } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');
const { GoogleGenerativeAI } = require('@google/generative-ai');

// Secret: Set via: firebase functions:secrets:set GOOGLE_AI_KEY
const googleAiKey = defineSecret('GOOGLE_AI_KEY');

/**
 * Callable Cloud Function: generateItinerary
 * Accepts { interests, days, location } from the client.
 * Uses Gemini 1.5 Flash to generate a trip plan as JSON.
 */
exports.generateItinerary = onCall(
  { secrets: [googleAiKey] },
  async (request) => {
    const apiKey = googleAiKey.value();

    if (!apiKey) {
      throw new Error('GOOGLE_AI_KEY is not configured');
    }

    const { interests, days, location } = request.data || {};

    if (!location) {
      throw new Error('location is required');
    }

    const interestsStr = Array.isArray(interests)
      ? interests.join(', ')
      : (interests || 'general sightseeing');
    const daysNum = parseInt(days, 10) || 3;

    const prompt = `Plan a ${daysNum} day trip to ${location} for someone interested in ${interestsStr}. Return valid JSON.`;

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });

    const result = await model.generateContent(prompt);
    const response = result.response;

    if (!response || !response.text) {
      throw new Error('No response from Gemini');
    }

    return { text: response.text() };
  }
);
