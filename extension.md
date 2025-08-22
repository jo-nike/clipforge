# ClipForge Browser Extension Development Plan

## Project Overview
Create Chrome and Firefox browser extensions that inject quick-clip buttons directly into the Plex web player interface, allowing users to create 30-second clips before/after the current playback position with a single click.

## Architecture

### 1. Extension Structure
```
clipforge-extension/
├── manifest.json (Chrome) / manifest.v2.json (Firefox)
├── src/
│   ├── background/
│   │   ├── background.js         # Service worker (Chrome) / Background script (Firefox)
│   │   ├── api-client.js         # ClipForge API communication
│   │   └── auth-manager.js       # Token management & refresh
│   ├── content/
│   │   ├── content.js            # Main content script
│   │   ├── plex-injector.js      # Button injection & player detection
│   │   ├── player-monitor.js     # Player state tracking
│   │   └── styles.css            # Injected button styles
│   ├── popup/
│   │   ├── popup.html            # Extension popup UI
│   │   ├── popup.js              # Popup logic
│   │   └── popup.css             # Popup styles
│   ├── options/
│   │   ├── options.html          # Settings page
│   │   ├── options.js            # Settings logic
│   │   └── options.css           # Settings styles
│   └── shared/
│       ├── constants.js          # Shared configuration
│       ├── utils.js              # Helper functions
│       └── storage.js            # Browser storage wrapper
├── icons/                        # Extension icons (16, 48, 128px)
├── build/                        # Build output
└── docs/
    └── extension.md             # This documentation
```

## Phase 1: Core Infrastructure

### 1.1 Manifest Configuration

**Chrome (Manifest V3):**
```json
{
  "manifest_version": 3,
  "name": "ClipForge for Plex",
  "version": "1.0.0",
  "description": "Create instant clips from Plex with one click",
  "permissions": [
    "storage",
    "tabs"
  ],
  "host_permissions": [
    "https://app.plex.tv/*",
    "https://watch.plex.tv/*",
    "http://localhost:8000/*",
    "<user_configured_api_url>"
  ],
  "background": {
    "service_worker": "src/background/background.js"
  },
  "content_scripts": [
    {
      "matches": ["https://app.plex.tv/*", "https://watch.plex.tv/*"],
      "js": ["src/content/content.js"],
      "css": ["src/content/styles.css"],
      "run_at": "document_idle"
    }
  ],
  "action": {
    "default_popup": "src/popup/popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  },
  "options_page": "src/options/options.html"
}
```

**Firefox (Manifest V2/V3 compatible):**
```json
{
  "manifest_version": 2,
  "name": "ClipForge for Plex",
  "version": "1.0.0",
  "permissions": [
    "storage",
    "tabs",
    "<all_urls>"
  ],
  "background": {
    "scripts": ["src/background/background.js"],
    "persistent": false
  },
  "content_scripts": [
    {
      "matches": ["*://app.plex.tv/*", "*://watch.plex.tv/*"],
      "js": ["src/content/content.js"],
      "css": ["src/content/styles.css"]
    }
  ],
  "browser_action": {
    "default_popup": "src/popup/popup.html"
  },
  "options_ui": {
    "page": "src/options/options.html"
  }
}
```

### 1.2 API Client Module

```javascript
// src/background/api-client.js
class ClipForgeAPI {
  constructor(baseUrl) {
    this.baseUrl = baseUrl || 'http://localhost:8000';
    this.token = null;
    this.plexToken = null;
  }

  async createQuickClip(sessionKey, startTime, endTime, title) {
    // Implementation for /api/v1/clips/create
  }

  async authenticate(plexToken) {
    // Implementation for /api/v1/auth/signin
  }

  async getCurrentSession() {
    // Implementation for /api/v1/sessions/current
  }
}
```

## Phase 2: Plex Player Integration

### 2.1 Player Detection & Monitoring

```javascript
// src/content/player-monitor.js
class PlexPlayerMonitor {
  constructor() {
    this.player = null;
    this.currentTime = 0;
    this.duration = 0;
    this.sessionKey = null;
    this.mediaInfo = null;
  }

  detectPlayer() {
    // Use MutationObserver to detect when player loads
    // Look for video element and player controls
  }

  extractSessionInfo() {
    // Extract session key from:
    // 1. URL parameters
    // 2. Player data attributes
    // 3. Plex's internal React props
  }

  trackPlaybackPosition() {
    // Listen to timeupdate events
    // Update currentTime continuously
  }
}
```

### 2.2 Button Injection

```javascript
// src/content/plex-injector.js
class PlexButtonInjector {
  injectButtons() {
    // Find close button in player controls
    const closeButton = this.findCloseButton();
    
    // Create button container
    const container = this.createButtonContainer();
    
    // Insert after close button
    closeButton.parentElement.insertBefore(container, closeButton.nextSibling);
  }

  findCloseButton() {
    // Multiple selector strategies:
    // 1. [aria-label="Close"]
    // 2. [data-testid="closeButton"]
    // 3. .PlayerControls-buttonGroup button:last-child
  }

  createButtonContainer() {
    // Create two buttons with Plex styling
    // Add click handlers
    // Add tooltips
  }
}
```

### 2.3 Button Styling

```css
/* src/content/styles.css */
.clipforge-button {
  background: transparent;
  border: none;
  color: #ffffff;
  cursor: pointer;
  padding: 8px;
  margin: 0 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
  display: inline-flex;
  align-items: center;
  font-size: 14px;
}

.clipforge-button:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.clipforge-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clipforge-button-icon {
  margin: 0 4px;
}

.clipforge-tooltip {
  position: absolute;
  bottom: 100%;
  background: rgba(0, 0, 0, 0.9);
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}
```

## Phase 3: Core Functionality

### 3.1 Quick Clip Creation

```javascript
// src/content/content.js
async function createQuickClip(direction) {
  const player = getPlexPlayer();
  const currentTime = player.currentTime;
  const duration = player.duration;
  
  let startTime, endTime;
  const clipDuration = getClipDuration(); // From settings, default 30
  
  if (direction === 'previous') {
    startTime = Math.max(0, currentTime - clipDuration);
    endTime = currentTime;
  } else {
    startTime = currentTime;
    endTime = Math.min(duration, currentTime + clipDuration);
  }
  
  // Send to background script
  chrome.runtime.sendMessage({
    action: 'createClip',
    data: {
      sessionKey: extractSessionKey(),
      startTime: formatTime(startTime),
      endTime: formatTime(endTime),
      title: generateClipTitle()
    }
  });
}
```

### 3.2 Time Formatting

```javascript
// src/shared/utils.js
function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
```

### 3.3 Session Detection

```javascript
// src/content/player-monitor.js
function extractSessionKey() {
  // Method 1: From URL
  const urlParams = new URLSearchParams(window.location.search);
  const key = urlParams.get('key');
  
  // Method 2: From player element
  const player = document.querySelector('video');
  const sessionKey = player?.getAttribute('data-session-key');
  
  // Method 3: From Plex's React internals
  const reactProps = getReactProps(player);
  
  return key || sessionKey || reactProps?.session?.key;
}
```

## Phase 4: Authentication Flow

### 4.1 Plex OAuth Integration

```javascript
// src/background/auth-manager.js
class AuthManager {
  async initiateAuth() {
    // 1. Create PIN with ClipForge API
    const pinResponse = await api.createAuthPin();
    
    // 2. Open Plex auth page
    const authUrl = `https://app.plex.tv/auth#?clientID=clipforge&code=${pinResponse.code}`;
    chrome.tabs.create({ url: authUrl });
    
    // 3. Poll for completion
    const token = await this.pollForToken(pinResponse.id);
    
    // 4. Sign in to ClipForge
    await api.signIn(token);
  }
  
  async pollForToken(pinId) {
    // Poll /api/v1/auth/pin/{pinId} every 2 seconds
  }
}
```

### 4.2 Token Storage

```javascript
// src/shared/storage.js
class SecureStorage {
  async saveTokens(authToken, plexToken) {
    await chrome.storage.local.set({
      authToken: authToken,
      plexToken: plexToken,
      tokenExpiry: Date.now() + (7 * 24 * 60 * 60 * 1000)
    });
  }
  
  async getTokens() {
    const data = await chrome.storage.local.get(['authToken', 'plexToken', 'tokenExpiry']);
    
    if (data.tokenExpiry < Date.now()) {
      await this.refreshTokens();
    }
    
    return data;
  }
}
```

## Phase 5: User Interface

### 5.1 Extension Popup

```html
<!-- src/popup/popup.html -->
<div class="popup-container">
  <div class="header">
    <img src="/icons/icon-48.png" alt="ClipForge">
    <h2>ClipForge for Plex</h2>
  </div>
  
  <div class="status-section">
    <div class="status-indicator" id="connectionStatus"></div>
    <span id="statusText">Not connected</span>
  </div>
  
  <div class="user-section" id="userInfo" style="display: none;">
    <img id="userAvatar" src="">
    <span id="username"></span>
  </div>
  
  <div class="actions">
    <button id="connectBtn">Connect to ClipForge</button>
    <button id="settingsBtn">Settings</button>
  </div>
  
  <div class="recent-clips" id="recentClips">
    <!-- Dynamically populated -->
  </div>
</div>
```

### 5.2 Options Page

```html
<!-- src/options/options.html -->
<div class="options-container">
  <h1>ClipForge Settings</h1>
  
  <section>
    <h2>API Configuration</h2>
    <label>
      API URL:
      <input type="url" id="apiUrl" placeholder="http://localhost:8000">
    </label>
  </section>
  
  <section>
    <h2>Clip Settings</h2>
    <label>
      Default clip duration:
      <select id="clipDuration">
        <option value="15">15 seconds</option>
        <option value="30" selected>30 seconds</option>
        <option value="60">1 minute</option>
        <option value="120">2 minutes</option>
      </select>
    </label>
    
    <label>
      <input type="checkbox" id="autoTitle">
      Auto-generate clip titles
    </label>
  </section>
  
  <section>
    <h2>Keyboard Shortcuts</h2>
    <label>
      Previous clip: <kbd id="prevShortcut">Alt + [</kbd>
    </label>
    <label>
      Next clip: <kbd id="nextShortcut">Alt + ]</kbd>
    </label>
  </section>
  
  <button id="saveBtn">Save Settings</button>
</div>
```

## Phase 6: Advanced Features

### 6.1 Keyboard Shortcuts

```javascript
// src/content/content.js
document.addEventListener('keydown', (event) => {
  if (event.altKey && event.key === '[') {
    event.preventDefault();
    createQuickClip('previous');
  } else if (event.altKey && event.key === ']') {
    event.preventDefault();
    createQuickClip('next');
  }
});
```

### 6.2 Visual Feedback

```javascript
// src/content/plex-injector.js
function showClipFeedback(button, success) {
  const originalText = button.textContent;
  
  if (success) {
    button.classList.add('success');
    button.textContent = '✓';
  } else {
    button.classList.add('error');
    button.textContent = '✗';
  }
  
  setTimeout(() => {
    button.classList.remove('success', 'error');
    button.textContent = originalText;
  }, 2000);
}
```

### 6.3 Error Handling

```javascript
// src/background/background.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'createClip') {
    api.createQuickClip(request.data)
      .then(response => {
        showNotification('Clip created successfully!', 'success');
        sendResponse({ success: true, clipId: response.clip_id });
      })
      .catch(error => {
        console.error('Clip creation failed:', error);
        showNotification('Failed to create clip', 'error');
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep channel open for async response
  }
});
```

## Phase 7: Testing Strategy

### 7.1 Unit Tests
- API client methods
- Time formatting utilities
- Session extraction logic

### 7.2 Integration Tests
- Button injection on different Plex layouts
- API communication with mock server
- Token refresh flow

### 7.3 E2E Tests
- Complete clip creation flow
- Authentication flow
- Settings persistence

## Phase 8: Deployment

### 8.1 Build Process

```json
// package.json
{
  "scripts": {
    "build:chrome": "webpack --config webpack.chrome.js",
    "build:firefox": "webpack --config webpack.firefox.js",
    "build:all": "npm run build:chrome && npm run build:firefox",
    "dev": "webpack --watch --config webpack.dev.js",
    "test": "jest",
    "lint": "eslint src/"
  }
}
```

### 8.2 Distribution
1. **Chrome Web Store**
   - Create developer account
   - Submit for review
   - Publish publicly or unlisted

2. **Firefox Add-ons**
   - Create Mozilla developer account
   - Submit for review
   - Sign extension

3. **Self-hosting**
   - Provide .crx/.xpi files
   - Installation instructions
   - Auto-update mechanism

## Security Considerations

1. **Token Security**
   - Never store tokens in plain text
   - Use browser's secure storage API
   - Implement token rotation

2. **Content Security Policy**
   - Strict CSP in manifest
   - No inline scripts
   - Validated message passing

3. **API Communication**
   - HTTPS only in production
   - Validate all responses
   - Rate limiting awareness

## Performance Optimizations

1. **Lazy Loading**
   - Load features on demand
   - Minimize initial bundle size

2. **Caching**
   - Cache user preferences
   - Cache recent clips list
   - Cache media metadata

3. **Debouncing**
   - Debounce player time updates
   - Throttle API requests

## User Documentation

1. **Installation Guide**
2. **Configuration Tutorial**
3. **Troubleshooting FAQ**
4. **Keyboard Shortcuts Reference**

## Maintenance Plan

1. **Version Updates**
   - Semantic versioning
   - Changelog maintenance
   - Migration scripts for settings

2. **Compatibility**
   - Monitor Plex player updates
   - Test on new browser versions
   - Maintain backwards compatibility

3. **User Feedback**
   - Error reporting system
   - Feature request tracking
   - User analytics (privacy-respecting)

This comprehensive plan provides a complete roadmap for building production-ready browser extensions that seamlessly integrate with both Plex and your ClipForge API.