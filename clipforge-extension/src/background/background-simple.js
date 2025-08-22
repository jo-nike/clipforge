import SimpleAuthManager from './auth-manager-simple.js';
import SimpleClipForgeAPI from './api-client-simple.js';

let authManager = null;
let api = null;

async function initialize() {
  authManager = new SimpleAuthManager();
  api = await authManager.initialize();
}

initialize();

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  handleMessage(request, sender, sendResponse);
  return true;
});

async function handleMessage(request, sender, sendResponse) {
  try {
    switch (request.action) {
      case 'createClip':
        await handleCreateClip(request.data, sendResponse);
        break;
        
      case 'testConnection':
        await handleTestConnection(sendResponse);
        break;
        
      case 'updateApiKey':
        await handleUpdateApiKey(request.data, sendResponse);
        break;
        
      case 'getUserInfo':
        await handleGetUserInfo(sendResponse);
        break;
        
      case 'isAuthenticated':
        await handleIsAuthenticated(sendResponse);
        break;
        
      case 'disconnect':
        await handleDisconnect(sendResponse);
        break;
        
      case 'getRecentClips':
        await handleGetRecentClips(sendResponse);
        break;
        
      case 'getSettings':
        await handleGetSettings(sendResponse);
        break;
        
      case 'saveSettings':
        await handleSaveSettings(request.data, sendResponse);
        break;
        
      default:
        sendResponse({ success: false, error: 'Unknown action' });
    }
  } catch (error) {
    console.error('Message handler error:', error);
    sendResponse({ success: false, error: error.message });
  }
}

async function handleCreateClip(data, sendResponse) {
  try {
    if (!await authManager.isAuthenticated()) {
      showNotification('Not connected', 'Please configure your API key first', 'error');
      sendResponse({ success: false, error: 'Not authenticated' });
      return;
    }
    
    const response = await api.createQuickClip(
      data.sessionKey,
      data.startTime,
      data.endTime,
      data.title
    );
    
    showNotification('Clip created!', `"${data.title}" has been created successfully`, 'success');
    sendResponse({ success: true, clipId: response.clip_id });
  } catch (error) {
    console.error('Clip creation failed:', error);
    showNotification('Clip creation failed', error.message, 'error');
    sendResponse({ success: false, error: error.message });
  }
}

async function handleTestConnection(sendResponse) {
  try {
    const isValid = await authManager.testConnection();
    sendResponse({ success: true, connected: isValid });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

async function handleUpdateApiKey(data, sendResponse) {
  try {
    const isValid = await authManager.updateApiKey(data.apiUrl, data.apiKey);
    sendResponse({ success: true, connected: isValid });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

async function handleGetUserInfo(sendResponse) {
  try {
    const userInfo = await authManager.getUserInfo();
    sendResponse({ success: true, user: userInfo });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

async function handleIsAuthenticated(sendResponse) {
  const isAuth = await authManager.isAuthenticated();
  sendResponse({ success: true, authenticated: isAuth });
}

async function handleDisconnect(sendResponse) {
  try {
    await authManager.disconnect();
    sendResponse({ success: true });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

async function handleGetRecentClips(sendResponse) {
  try {
    if (!await authManager.isAuthenticated()) {
      sendResponse({ success: false, error: 'Not authenticated' });
      return;
    }
    
    const clips = await api.getRecentClips();
    sendResponse({ success: true, clips: clips });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

async function handleGetSettings(sendResponse) {
  const settings = await chrome.storage.sync.get({
    apiUrl: 'http://localhost:8002',
    apiKey: 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
    clipDuration: 30,
    autoTitle: true,
    prevShortcut: 'Alt+[',
    nextShortcut: 'Alt+]'
  });
  sendResponse({ success: true, settings: settings });
}

async function handleSaveSettings(settings, sendResponse) {
  try {
    await chrome.storage.sync.set(settings);
    
    // If API settings changed, reinitialize
    if (settings.apiUrl || settings.apiKey) {
      await initialize();
    }
    
    sendResponse({ success: true });
  } catch (error) {
    sendResponse({ success: false, error: error.message });
  }
}

function showNotification(title, message, type = 'basic') {
  const iconPath = type === 'error' ? 'icons/icon-48-error.png' : 'icons/icon-48.png';
  
  chrome.notifications.create({
    type: 'basic',
    iconUrl: iconPath,
    title: title,
    message: message,
    priority: type === 'error' ? 2 : 1
  });
}

chrome.runtime.onInstalled.addListener(() => {
  console.log('ClipForge extension installed (Simple API Key version)');
  
  chrome.storage.sync.get(['apiUrl', 'apiKey'], (result) => {
    if (!result.apiUrl) {
      chrome.storage.sync.set({
        apiUrl: 'http://localhost:8002',
        apiKey: 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
        clipDuration: 30,
        autoTitle: true
      });
    }
  });
});