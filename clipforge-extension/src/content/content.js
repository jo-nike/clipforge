(function() {
  let playerMonitor = null;
  let buttonInjector = null;
  let settings = {};
  let isInitialized = false;

  async function initialize() {
    if (isInitialized) return;
    isInitialized = true;

    console.log('ClipForge: Initializing content script');

    await loadSettings();

    const PlexPlayerMonitor = (await import('./player-monitor.js')).default;
    const PlexButtonInjector = (await import('./plex-injector.js')).default;

    playerMonitor = new PlexPlayerMonitor();
    buttonInjector = new PlexButtonInjector();

    const playerDetected = await playerMonitor.detectPlayer();
    
    if (playerDetected) {
      console.log('ClipForge: Player detected');
      playerMonitor.extractSessionInfo();
      await buttonInjector.inject();
      buttonInjector.updateSettings(settings);
      setupEventListeners();
      setupKeyboardShortcuts();
    } else {
      console.log('ClipForge: No player detected, watching for changes');
      observeForPlayer();
    }
  }

  async function loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.sync.get({
        clipDuration: 30,
        autoTitle: true,
        prevShortcut: 'Alt+[',
        nextShortcut: 'Alt+]'
      }, (result) => {
        settings = result;
        resolve();
      });
    });
  }

  function setupEventListeners() {
    document.addEventListener('clipforge-create-clip', async (event) => {
      const direction = event.detail.direction;
      await createQuickClip(direction);
    });

    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'updateSettings') {
        settings = request.settings;
        if (buttonInjector) {
          buttonInjector.updateSettings(settings);
        }
      }
    });
  }

  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (event) => {
      if (!playerMonitor || !playerMonitor.player) return;

      const prevKey = parseShortcut(settings.prevShortcut);
      const nextKey = parseShortcut(settings.nextShortcut);

      if (matchesShortcut(event, prevKey)) {
        event.preventDefault();
        createQuickClip('previous');
      } else if (matchesShortcut(event, nextKey)) {
        event.preventDefault();
        createQuickClip('next');
      }
    });
  }

  function parseShortcut(shortcut) {
    const parts = shortcut.split('+');
    return {
      altKey: parts.includes('Alt'),
      ctrlKey: parts.includes('Ctrl'),
      shiftKey: parts.includes('Shift'),
      metaKey: parts.includes('Meta') || parts.includes('Cmd'),
      key: parts[parts.length - 1].replace(/[\[\]]/g, '')
    };
  }

  function matchesShortcut(event, shortcut) {
    return event.altKey === shortcut.altKey &&
           event.ctrlKey === shortcut.ctrlKey &&
           event.shiftKey === shortcut.shiftKey &&
           event.metaKey === shortcut.metaKey &&
           event.key === shortcut.key;
  }

  async function createQuickClip(direction) {
    if (!playerMonitor) {
      console.error('ClipForge: Player monitor not initialized');
      return;
    }

    const playbackInfo = playerMonitor.getCurrentPlaybackInfo();
    
    if (!playbackInfo.sessionKey && !playbackInfo.mediaInfo.ratingKey) {
      console.error('ClipForge: No session key or rating key found');
      if (buttonInjector) {
        buttonInjector.updateButtonStatus(direction, 'error');
      }
      return;
    }

    const clipDuration = settings.clipDuration || 30;
    let startTime, endTime;

    if (direction === 'previous') {
      startTime = Math.max(0, playbackInfo.currentTime - clipDuration);
      endTime = playbackInfo.currentTime;
    } else {
      startTime = playbackInfo.currentTime;
      endTime = Math.min(playbackInfo.duration, playbackInfo.currentTime + clipDuration);
    }

    const title = settings.autoTitle 
      ? playerMonitor.generateClipTitle(direction)
      : `Clip at ${formatTime(startTime)}`;

    try {
      const response = await chrome.runtime.sendMessage({
        action: 'createClip',
        data: {
          sessionKey: playbackInfo.sessionKey || playbackInfo.mediaInfo.ratingKey,
          startTime: formatTime(startTime),
          endTime: formatTime(endTime),
          title: title
        }
      });

      if (response.success) {
        console.log('ClipForge: Clip created successfully');
        if (buttonInjector) {
          buttonInjector.updateButtonStatus(direction, 'success');
        }
      } else {
        console.error('ClipForge: Clip creation failed:', response.error);
        if (buttonInjector) {
          buttonInjector.updateButtonStatus(direction, 'error');
        }
      }
    } catch (error) {
      console.error('ClipForge: Error creating clip:', error);
      if (buttonInjector) {
        buttonInjector.updateButtonStatus(direction, 'error');
      }
    }
  }

  function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  function observeForPlayer() {
    const observer = new MutationObserver(async () => {
      const video = document.querySelector('video');
      if (video && !isInitialized) {
        observer.disconnect();
        await initialize();
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }

  window.addEventListener('popstate', () => {
    if (playerMonitor) {
      playerMonitor.destroy();
    }
    if (buttonInjector) {
      buttonInjector.destroy();
    }
    isInitialized = false;
    setTimeout(initialize, 1000);
  });
})();