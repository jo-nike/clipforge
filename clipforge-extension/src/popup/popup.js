const elements = {
  connectionStatus: document.getElementById('connectionStatus'),
  statusText: document.getElementById('statusText'),
  userInfo: document.getElementById('userInfo'),
  userAvatar: document.getElementById('userAvatar'),
  username: document.getElementById('username'),
  userEmail: document.getElementById('userEmail'),
  connectBtn: document.getElementById('connectBtn'),
  disconnectBtn: document.getElementById('disconnectBtn'),
  settingsBtn: document.getElementById('settingsBtn'),
  recentClips: document.getElementById('recentClips'),
  clipsList: document.getElementById('clipsList')
};

async function initialize() {
  await checkAuthStatus();
  setupEventListeners();
}

async function checkAuthStatus() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'isAuthenticated' });
    
    if (response.success && response.authenticated) {
      await loadUserInfo();
      await loadRecentClips();
      updateUI('connected');
    } else {
      updateUI('disconnected');
    }
  } catch (error) {
    console.error('Failed to check auth status:', error);
    updateUI('disconnected');
  }
}

async function loadUserInfo() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getUserInfo' });
    
    if (response.success && response.user) {
      elements.username.textContent = response.user.username || response.user.email;
      elements.userEmail.textContent = response.user.email || '';
      
      if (response.user.thumb) {
        elements.userAvatar.src = response.user.thumb;
      } else {
        elements.userAvatar.src = '/icons/icon-48.png';
      }
    }
  } catch (error) {
    console.error('Failed to load user info:', error);
  }
}

async function loadRecentClips() {
  try {
    elements.clipsList.innerHTML = '<div class="loading">Loading clips...</div>';
    
    const response = await chrome.runtime.sendMessage({ action: 'getRecentClips' });
    
    if (response.success && response.clips) {
      displayClips(response.clips);
    } else {
      elements.clipsList.innerHTML = '<div class="error-message">Failed to load clips</div>';
    }
  } catch (error) {
    console.error('Failed to load recent clips:', error);
    elements.clipsList.innerHTML = '<div class="error-message">Failed to load clips</div>';
  }
}

function displayClips(clips) {
  if (!clips || clips.length === 0) {
    elements.clipsList.innerHTML = '<div class="loading">No clips yet</div>';
    return;
  }
  
  elements.clipsList.innerHTML = '';
  
  clips.forEach(clip => {
    const clipElement = createClipElement(clip);
    elements.clipsList.appendChild(clipElement);
  });
}

function createClipElement(clip) {
  const div = document.createElement('div');
  div.className = 'clip-item';
  
  const title = document.createElement('div');
  title.className = 'clip-title';
  title.textContent = clip.title || 'Untitled Clip';
  
  const meta = document.createElement('div');
  meta.className = 'clip-meta';
  
  const duration = document.createElement('span');
  duration.textContent = formatDuration(clip.duration);
  
  const date = document.createElement('span');
  date.textContent = formatDate(clip.created_at);
  
  meta.appendChild(duration);
  meta.appendChild(date);
  
  div.appendChild(title);
  div.appendChild(meta);
  
  div.addEventListener('click', () => {
    chrome.tabs.create({ url: `http://localhost:8000/clips/${clip.id}` });
  });
  
  return div;
}

function formatDuration(seconds) {
  if (!seconds) return '0s';
  
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  
  if (mins > 0) {
    return `${mins}m ${secs}s`;
  }
  return `${secs}s`;
}

function formatDate(dateString) {
  if (!dateString) return '';
  
  const date = new Date(dateString);
  const now = new Date();
  const diff = now - date;
  
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  
  return date.toLocaleDateString();
}

function updateUI(status) {
  if (status === 'connected') {
    elements.connectionStatus.className = 'status-indicator connected';
    elements.statusText.textContent = 'Connected to ClipForge';
    elements.userInfo.style.display = 'flex';
    elements.connectBtn.style.display = 'none';
    elements.disconnectBtn.style.display = 'block';
    elements.recentClips.style.display = 'flex';
  } else {
    elements.connectionStatus.className = 'status-indicator disconnected';
    elements.statusText.textContent = 'Not connected';
    elements.userInfo.style.display = 'none';
    elements.connectBtn.style.display = 'block';
    elements.disconnectBtn.style.display = 'none';
    elements.recentClips.style.display = 'none';
  }
}

function setupEventListeners() {
  elements.connectBtn.addEventListener('click', async () => {
    elements.connectBtn.disabled = true;
    elements.connectBtn.textContent = 'Connecting...';
    
    try {
      const response = await chrome.runtime.sendMessage({ action: 'authenticate' });
      
      if (response.success) {
        await checkAuthStatus();
      } else {
        alert('Authentication failed: ' + (response.error || 'Unknown error'));
      }
    } catch (error) {
      console.error('Authentication error:', error);
      alert('Failed to connect to ClipForge');
    } finally {
      elements.connectBtn.disabled = false;
      elements.connectBtn.textContent = 'Connect to ClipForge';
    }
  });
  
  elements.disconnectBtn.addEventListener('click', async () => {
    if (confirm('Are you sure you want to disconnect from ClipForge?')) {
      try {
        await chrome.runtime.sendMessage({ action: 'logout' });
        updateUI('disconnected');
      } catch (error) {
        console.error('Logout error:', error);
      }
    }
  });
  
  elements.settingsBtn.addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
  });
}

document.addEventListener('DOMContentLoaded', initialize);