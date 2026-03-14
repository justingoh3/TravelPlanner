import '../styles/globals.css'
import Head from 'next/head'
import { initFirebase } from '../lib/firebase'

// Initialize Firebase (required for aiPlanner Cloud Function calls)
if (typeof window !== 'undefined') {
  initFirebase()
}

export default function App({ Component, pageProps }) {
  return (
    <>
      <Head>
        {/* Preconnect to Google Maps for faster loading */}
        <link rel="preconnect" href="https://maps.googleapis.com" />
        <link rel="dns-prefetch" href="https://maps.googleapis.com" />
      </Head>
      <Component {...pageProps} />
    </>
  )
}

