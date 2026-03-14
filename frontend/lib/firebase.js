/**
 * Firebase configuration - Initialize once (e.g. in _app.js)
 * Get your config from Firebase Console > Project Settings > General
 */

import { initializeApp, getApps } from 'firebase/app';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID
};

export function initFirebase() {
  if (typeof window === 'undefined') return null;
  if (getApps().length > 0) return getApps()[0];
  return initializeApp(firebaseConfig);
}
