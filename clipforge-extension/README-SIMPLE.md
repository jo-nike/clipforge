# ClipForge Browser Extension - Simple API Key Version

This is a simplified version of the ClipForge browser extension that uses API key authentication instead of Plex OAuth.

## Quick Start

1. **Start your ClipForge API server**:
   ```bash
   cd backend
   python3 main.py
   ```

2. **Load the extension in Chrome**:
   - Go to `chrome://extensions/`
   - Enable Developer mode
   - Click "Load unpacked"
   - Select the `clipforge-extension` folder

3. **Configure the extension**:
   - Click the extension icon
   - Click the settings button
   - Enter your API URL: `http://localhost:8002`
   - Enter the test API key: `cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`
   - Click "Test Connection" to verify
   - Click "Save Settings"

4. **Use the extension**:
   - Navigate to any video in Plex web player
   - Use the injected [-30s] and [+30s] buttons
   - Or use keyboard shortcuts: Alt+[ and Alt+]

## Default Test API Key

For testing purposes, the extension comes with a default API key:
```
cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

This key is configured in both:
- Backend: `/backend/core/constants.py`
- Extension: Default value in settings

## How It Works

1. **No OAuth Required**: Uses a simple API key for authentication
2. **Direct API Access**: All requests include the `X-API-Key` header
3. **Simplified Flow**: No popups, redirects, or complex authentication
4. **Instant Connection**: Just enter your API key and you're connected

## API Key Authentication

The extension sends the API key in the `X-API-Key` header with every request:
```javascript
headers: {
  'Content-Type': 'application/json',
  'X-API-Key': 'your_api_key_here'
}
```

The backend validates the key and allows access to:
- `/api/v1/auth/*`
- `/api/v1/clips/*`
- `/api/v1/sessions/*`
- `/api/v1/storage/*`
- `/api/v1/users/*`

## Files Changed for Simple Version

- `src/background/background-simple.js` - Simplified background script
- `src/background/api-client-simple.js` - API client with API key auth
- `src/background/auth-manager-simple.js` - Simple auth manager
- `src/popup/popup-simple.js` - Simplified popup
- `manifest.json` - Points to simple background script
- Options page - Added API key field

## Production Considerations

For production use:
1. Generate unique API keys per user
2. Store API keys securely in database
3. Implement proper key rotation
4. Add rate limiting per API key
5. Log API key usage for auditing

## Troubleshooting

### Connection Failed
- Ensure ClipForge API is running on the correct port
- Check the API URL in settings (default: `http://localhost:8002`)
- Verify the API key is correct (minimum 32 characters)

### 403 Forbidden
- The API key might be invalid
- Check backend logs for validation errors

### CORS Issues
- The backend has been configured to allow browser extensions
- Restart the API server after any configuration changes