# Firebase + Gemini AI Setup

## Task 3: Set the Secret Key

Run this command to store your Google AI Studio API key securely in Firebase Secret Manager:

```bash
firebase functions:secrets:set GOOGLE_AI_KEY
```

You will be prompted to enter the secret value. Paste your API key (e.g. `AIza...`) when prompted.

**Alternative (non-interactive):**
```bash
echo -n "YOUR_AI_KEY_HERE" | firebase functions:secrets:set GOOGLE_AI_KEY
```

After setting the secret, redeploy your functions:
```bash
firebase deploy --only functions
```

---

## Full Setup Checklist

1. **Firebase project**: Run `firebase login` and `firebase init` if not done
2. **Install functions deps**: `cd functions && npm install`
3. **Set secret**: `firebase functions:secrets:set GOOGLE_AI_KEY`
4. **Deploy**: `firebase deploy --only functions`
5. **Frontend env**: Add Firebase config to `frontend/.env.local` (see `.env.local.example`)
