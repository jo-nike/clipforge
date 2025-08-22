# Fixing CORS Issues for Browser Extension

## The Problem
Browser extensions make requests with origins like:
- Chrome: `chrome-extension://[extension-id]`
- Firefox: `moz-extension://[extension-id]`

These need to be explicitly allowed in your ClipForge API CORS configuration.

## Solution for FastAPI (Python)

If your ClipForge API uses FastAPI, update your CORS middleware:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configure CORS to allow browser extensions
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Your web app
        "https://app.plex.tv",
        "https://watch.plex.tv",
        "chrome-extension://*",    # Allow all Chrome extensions
        "moz-extension://*"         # Allow all Firefox extensions
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OR more permissive (for development):
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Solution for Express (Node.js)

If using Express:

```javascript
const cors = require('cors');

const corsOptions = {
  origin: function (origin, callback) {
    // Allow requests with no origin (like mobile apps or Postman)
    if (!origin) return callback(null, true);
    
    // Allow browser extensions
    if (origin.startsWith('chrome-extension://') || 
        origin.startsWith('moz-extension://')) {
      return callback(null, true);
    }
    
    // Allow specific origins
    const allowedOrigins = [
      'http://localhost:3000',
      'https://app.plex.tv',
      'https://watch.plex.tv'
    ];
    
    if (allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
};

app.use(cors(corsOptions));

// OR simpler for development:
app.use(cors({
  origin: '*',
  credentials: true
}));
```

## Solution for Django

If using Django:

```python
# settings.py
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://app.plex.tv",
    "https://watch.plex.tv",
]

# Allow browser extensions
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^chrome-extension://.*$",
    r"^moz-extension://.*$",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_HEADERS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# OR for development:
CORS_ORIGIN_ALLOW_ALL = True  # Caution: Only use in development!
```

## Quick Test

After updating your API server's CORS configuration:

1. Restart your ClipForge API server
2. Reload the browser extension
3. Try connecting again

## Alternative: Proxy Requests (Workaround)

If you can't modify the API server, you can route requests through the background script which doesn't have CORS restrictions:

```javascript
// In content script - send to background instead of direct API call
chrome.runtime.sendMessage({
  action: 'apiRequest',
  endpoint: '/api/v1/auth/pin',
  method: 'POST',
  body: { /* data */ }
});

// Background script already handles this properly
```

## Note on Port 8002

I notice your API is running on port 8002, but the extension defaults to 8000. Make sure to:

1. Update the API URL in extension settings to `http://localhost:8002`
2. Or update the manifest.json to include port 8002 in host_permissions:

```json
"host_permissions": [
  "http://localhost:8000/*",
  "http://localhost:8001/*",
  "http://localhost:8002/*"  // Add this
]
```

## Security Considerations

For production:
- Don't use `allow_origins=["*"]` 
- Specifically whitelist your extension ID once published
- Use HTTPS for production API endpoints