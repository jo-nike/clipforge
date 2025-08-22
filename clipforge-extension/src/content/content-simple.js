(function() {
  let settings = {
    clipDuration: 30,
    autoTitle: true
  };
  let buttonsInjected = false;
  let prevButton = null;
  let nextButton = null;

  console.log('ClipForge: Starting simple content script');

  // Load settings
  chrome.storage.sync.get({
    clipDuration: 30,
    autoTitle: true,
    apiUrl: 'http://localhost:8002',
    apiKey: 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
  }, (result) => {
    settings = result;
    console.log('ClipForge: Settings loaded', settings);
    injectButtons();
  });

  function injectButtons() {
    if (buttonsInjected) return;

    console.log('ClipForge: Attempting to inject buttons');

    // Create a floating button container
    const container = document.createElement('div');
    container.id = 'clipforge-floating-buttons';
    container.style.cssText = `
      position: fixed;
      bottom: 100px;
      right: 20px;
      z-index: 999999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: rgba(0, 0, 0, 0.8);
      padding: 10px;
      border-radius: 8px;
      border: 2px solid #667eea;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    `;

    // Create previous button
    prevButton = document.createElement('button');
    prevButton.textContent = `⏪ Clip Last ${settings.clipDuration}s`;
    prevButton.style.cssText = `
      padding: 10px 15px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      min-width: 150px;
      transition: all 0.3s;
    `;
    prevButton.onmouseover = () => {
      prevButton.style.transform = 'scale(1.05)';
    };
    prevButton.onmouseout = () => {
      prevButton.style.transform = 'scale(1)';
    };
    prevButton.onclick = () => createClip('previous');

    // Create next button
    nextButton = document.createElement('button');
    nextButton.textContent = `⏩ Clip Next ${settings.clipDuration}s`;
    nextButton.style.cssText = `
      padding: 10px 15px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      min-width: 150px;
      transition: all 0.3s;
    `;
    nextButton.onmouseover = () => {
      nextButton.style.transform = 'scale(1.05)';
    };
    nextButton.onmouseout = () => {
      nextButton.style.transform = 'scale(1)';
    };
    nextButton.onclick = () => createClip('next');

    // Add ClipForge label
    const label = document.createElement('div');
    label.textContent = 'ClipForge';
    label.style.cssText = `
      color: #667eea;
      font-size: 12px;
      font-weight: bold;
      text-align: center;
      margin-bottom: 5px;
    `;

    container.appendChild(label);
    container.appendChild(prevButton);
    container.appendChild(nextButton);

    document.body.appendChild(container);
    buttonsInjected = true;

    console.log('ClipForge: Floating buttons injected!');

    // Also try to inject into player controls if they exist
    injectIntoPlayerControls();
  }

  function injectIntoPlayerControls() {
    // Try to find player controls every few seconds
    const checkInterval = setInterval(() => {
      const playerControls = document.querySelector('[aria-label="Player Controls"], [class*="PlayerControls"], .video-controls, .player-controls');
      
      if (playerControls && !document.getElementById('clipforge-player-buttons')) {
        console.log('ClipForge: Found player controls, injecting buttons there too');
        
        const playerContainer = document.createElement('div');
        playerContainer.id = 'clipforge-player-buttons';
        playerContainer.style.cssText = `
          display: inline-flex;
          gap: 5px;
          margin: 0 10px;
        `;

        const prevBtn = document.createElement('button');
        prevBtn.textContent = `[-${settings.clipDuration}s]`;
        prevBtn.style.cssText = `
          background: transparent;
          color: white;
          border: 1px solid rgba(255, 255, 255, 0.3);
          border-radius: 4px;
          padding: 5px 10px;
          cursor: pointer;
          font-size: 12px;
        `;
        prevBtn.onclick = () => createClip('previous');

        const nextBtn = document.createElement('button');
        nextBtn.textContent = `[+${settings.clipDuration}s]`;
        nextBtn.style.cssText = `
          background: transparent;
          color: white;
          border: 1px solid rgba(255, 255, 255, 0.3);
          border-radius: 4px;
          padding: 5px 10px;
          cursor: pointer;
          font-size: 12px;
        `;
        nextBtn.onclick = () => createClip('next');

        playerContainer.appendChild(prevBtn);
        playerContainer.appendChild(nextBtn);
        
        // Try to insert near other buttons
        const closeButton = playerControls.querySelector('[aria-label="Close"], [title="Close"], button[class*="close"]');
        if (closeButton && closeButton.parentElement) {
          closeButton.parentElement.insertBefore(playerContainer, closeButton);
        } else {
          playerControls.appendChild(playerContainer);
        }
      }
    }, 2000);

    // Stop checking after 1 minute
    setTimeout(() => clearInterval(checkInterval), 60000);
  }

  async function createClip(direction) {
    console.log('ClipForge: Creating clip', direction);

    // Get video element
    const video = document.querySelector('video');
    if (!video) {
      alert('ClipForge: No video found on page');
      return;
    }

    const currentTime = video.currentTime;
    const duration = video.duration;
    const clipDuration = settings.clipDuration || 30;

    let startTime, endTime;
    if (direction === 'previous') {
      startTime = Math.max(0, currentTime - clipDuration);
      endTime = currentTime;
    } else {
      startTime = currentTime;
      endTime = Math.min(duration, currentTime + clipDuration);
    }

    // Try to get the active Plex session first
    const sessionInfo = await getActiveSession();
    const sessionKey = sessionInfo ? sessionInfo.key : extractSessionKey();
    const title = generateClipTitle(direction, currentTime);

    // Show feedback
    const button = direction === 'previous' ? prevButton : nextButton;
    const originalText = button.textContent;
    button.textContent = '⏳ Creating...';
    button.disabled = true;

    try {
      // Log what we're sending
      console.log('ClipForge: Sending clip request with session:', sessionKey);
      
      const response = await chrome.runtime.sendMessage({
        action: 'createClip',
        data: {
          sessionKey: null,  // Let backend get the current session
          startTime: formatTime(startTime),
          endTime: formatTime(endTime),
          title: title
        }
      });

      if (response && response.success) {
        button.textContent = '✅ Created!';
        button.style.background = 'linear-gradient(135deg, #4caf50 0%, #45a049 100%)';
        
        setTimeout(() => {
          button.textContent = originalText;
          button.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
          button.disabled = false;
        }, 2000);
      } else {
        throw new Error(response?.error || 'Failed to create clip');
      }
    } catch (error) {
      console.error('ClipForge: Error creating clip:', error);
      button.textContent = '❌ Failed';
      button.style.background = 'linear-gradient(135deg, #f44336 0%, #da190b 100%)';
      
      setTimeout(() => {
        button.textContent = originalText;
        button.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        button.disabled = false;
      }, 2000);
      
      alert('ClipForge: ' + error.message);
    }
  }

  async function getActiveSession() {
    // Try to get the active session from Plex by calling the sessions endpoint
    try {
      // First, we need to get the Plex server URL and token from the page
      const plexToken = getPlexToken();
      if (!plexToken) {
        console.log('ClipForge: No Plex token found');
        return null;
      }

      // Get the server URL from the current page
      const serverMatch = window.location.hostname.match(/(\d+\-[a-f0-9\-]+)\..*\.plex\.direct/);
      let serverUrl = '';
      
      if (serverMatch) {
        // Direct connection
        serverUrl = window.location.origin;
      } else if (window.location.hostname === 'app.plex.tv') {
        // Need to find the server URL from the page
        // This is complex and might not work reliably
        console.log('ClipForge: Running on app.plex.tv, cannot get direct server access');
        return null;
      }

      if (!serverUrl) {
        return null;
      }

      // Call the Plex sessions endpoint
      const response = await fetch(`${serverUrl}/status/sessions`, {
        headers: {
          'X-Plex-Token': plexToken,
          'Accept': 'application/json'
        }
      });

      if (!response.ok) {
        console.log('ClipForge: Failed to get sessions:', response.status);
        return null;
      }

      const data = await response.json();
      
      // Find the session that matches our current video
      const video = document.querySelector('video');
      if (!video || !data.MediaContainer || !data.MediaContainer.Metadata) {
        return null;
      }

      // Try to match by current time or other properties
      const currentTime = Math.floor(video.currentTime * 1000); // Convert to milliseconds
      
      for (const session of data.MediaContainer.Metadata) {
        // Check if this session is close to our current playback position
        const sessionTime = parseInt(session.viewOffset || 0);
        const timeDiff = Math.abs(sessionTime - currentTime);
        
        // If within 5 seconds, probably our session
        if (timeDiff < 5000) {
          console.log('ClipForge: Found matching session:', session.sessionKey);
          return {
            key: session.sessionKey,
            mediaKey: session.ratingKey
          };
        }
      }

      console.log('ClipForge: No matching session found in active sessions');
      return null;
    } catch (error) {
      console.error('ClipForge: Error getting active session:', error);
      return null;
    }
  }

  function getPlexToken() {
    // Try multiple methods to get the Plex token
    
    // Method 1: From localStorage
    try {
      const stored = localStorage.getItem('myPlexAccessToken');
      if (stored) {
        return stored.replace(/"/g, '');
      }
    } catch (e) {}

    // Method 2: From cookies
    try {
      const cookies = document.cookie.split(';');
      for (const cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'plex_token' || name === 'plexToken') {
          return value;
        }
      }
    } catch (e) {}

    // Method 3: From the page's JavaScript context (this won't work due to isolation)
    // But we can try to find it in script tags or data attributes
    const tokenElement = document.querySelector('[data-plex-token]');
    if (tokenElement) {
      return tokenElement.getAttribute('data-plex-token');
    }

    return null;
  }

  function extractSessionKey() {
    // Try multiple methods to get the session key
    let key = null;

    // Method 1: Check URL params
    const urlParams = new URLSearchParams(window.location.search);
    key = urlParams.get('key');
    
    // Method 2: Extract from URL path (for metadata items)
    if (!key) {
      const pathMatch = window.location.pathname.match(/\/metadata\/(\d+)/);
      if (pathMatch) {
        key = pathMatch[1];
      }
    }

    // Method 3: Look for video element with data attributes
    if (!key) {
      const video = document.querySelector('video');
      if (video) {
        // Check various data attributes
        key = video.getAttribute('data-session-key') || 
              video.getAttribute('data-media-key') ||
              video.getAttribute('data-key');
      }
    }

    // Method 4: Try to find it in the page's React props or data
    if (!key) {
      // Look for elements with key information
      const elements = document.querySelectorAll('[data-key], [data-media-index], [data-testid*="metadata"]');
      for (const el of elements) {
        const dataKey = el.getAttribute('data-key');
        if (dataKey && dataKey.match(/^\d+$/)) {
          key = dataKey;
          break;
        }
      }
    }

    // Method 5: Extract from the Plex Web UI state
    if (!key) {
      // Try to find the current playing item's key from various sources
      try {
        // Check if there's a poster image with metadata ID
        const poster = document.querySelector('img[src*="/photo/"], img[src*="/thumb/"]');
        if (poster && poster.src) {
          const thumbMatch = poster.src.match(/\/library\/metadata\/(\d+)\//);
          if (thumbMatch) {
            key = thumbMatch[1];
          }
        }
      } catch (e) {
        console.log('ClipForge: Error extracting from poster:', e);
      }
    }

    // Method 6: Check for server/key pattern in URL
    if (!key) {
      const serverKeyMatch = window.location.pathname.match(/\/server\/([^\/]+)\/details/);
      if (serverKeyMatch) {
        // Extract from the details URL
        const urlKey = urlParams.get('key') || urlParams.get('item');
        if (urlKey) {
          key = urlKey.replace('/library/metadata/', '');
        }
      }
    }

    // If still no key, try to get active session from Plex
    if (!key) {
      // Look for the playing item indicator
      const playingItem = document.querySelector('[class*="PlayingItem"], [class*="nowPlaying"], [aria-label*="Now Playing"]');
      if (playingItem) {
        const link = playingItem.querySelector('a[href*="/metadata/"]');
        if (link) {
          const match = link.href.match(/\/metadata\/(\d+)/);
          if (match) {
            key = match[1];
          }
        }
      }
    }

    // Fallback: Use a test session key that might work
    if (!key) {
      console.warn('ClipForge: Could not extract session key, using fallback');
      // Try to get any metadata ID from the page
      const anyMetadata = document.querySelector('[href*="/metadata/"]');
      if (anyMetadata) {
        const match = anyMetadata.href.match(/\/metadata\/(\d+)/);
        if (match) {
          key = match[1];
        }
      } else {
        // Use a placeholder that might work with test mode
        key = 'test_session';
      }
    }

    console.log('ClipForge: Extracted session key:', key);
    return key;
  }

  function generateClipTitle(direction, currentTime) {
    const titleElement = document.querySelector('[data-testid="metadata-title"], h1, .video-title');
    const baseTitle = titleElement ? titleElement.textContent.trim() : 'Plex Video';
    
    const timestamp = formatTimestamp(currentTime);
    const directionText = direction === 'previous' ? 'before' : 'after';
    
    return `${baseTitle} - Clip ${directionText} ${timestamp}`;
  }

  function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  function formatTimestamp(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}h${minutes}m${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', (event) => {
    if (event.altKey && event.key === '[') {
      event.preventDefault();
      createClip('previous');
    } else if (event.altKey && event.key === ']') {
      event.preventDefault();
      createClip('next');
    }
  });

  // Hide/show buttons based on video presence
  setInterval(() => {
    const video = document.querySelector('video');
    const container = document.getElementById('clipforge-floating-buttons');
    
    if (container) {
      if (video) {
        container.style.display = 'flex';
      } else {
        container.style.display = 'none';
      }
    }
  }, 1000);

  console.log('ClipForge: Simple content script loaded and ready!');
})();