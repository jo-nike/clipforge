const elements = {
  apiUrl: document.getElementById('apiUrl'),
  apiKey: document.getElementById('apiKey'),
  testConnectionBtn: document.getElementById('testConnectionBtn'),
  connectionStatus: document.getElementById('connectionStatus'),
  clipDuration: document.getElementById('clipDuration'),
  autoTitle: document.getElementById('autoTitle'),
  debugMode: document.getElementById('debugMode'),
  notifications: document.getElementById('notifications'),
  prevShortcut: document.getElementById('prevShortcut'),
  nextShortcut: document.getElementById('nextShortcut'),
  editPrevShortcut: document.getElementById('editPrevShortcut'),
  editNextShortcut: document.getElementById('editNextShortcut'),
  saveBtn: document.getElementById('saveBtn'),
  resetBtn: document.getElementById('resetBtn'),
  statusMessage: document.getElementById('statusMessage'),
  shortcutModal: document.getElementById('shortcutModal'),
  shortcutDisplay: document.getElementById('shortcutDisplay'),
  shortcutCancel: document.getElementById('shortcutCancel'),
  shortcutSave: document.getElementById('shortcutSave')
};

let currentShortcutEdit = null;
let pendingShortcut = null;

async function loadSettings() {
  const settings = await chrome.storage.sync.get({
    apiUrl: 'http://localhost:8002',
    apiKey: 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
    clipDuration: 30,
    autoTitle: true,
    debugMode: false,
    notifications: true,
    prevShortcut: 'Alt+[',
    nextShortcut: 'Alt+]'
  });
  
  elements.apiUrl.value = settings.apiUrl;
  elements.apiKey.value = settings.apiKey;
  elements.clipDuration.value = settings.clipDuration;
  elements.autoTitle.checked = settings.autoTitle;
  elements.debugMode.checked = settings.debugMode;
  elements.notifications.checked = settings.notifications;
  elements.prevShortcut.textContent = settings.prevShortcut;
  elements.nextShortcut.textContent = settings.nextShortcut;
}

async function saveSettings() {
  const settings = {
    apiUrl: elements.apiUrl.value || 'http://localhost:8002',
    apiKey: elements.apiKey.value || 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
    clipDuration: parseInt(elements.clipDuration.value),
    autoTitle: elements.autoTitle.checked,
    debugMode: elements.debugMode.checked,
    notifications: elements.notifications.checked,
    prevShortcut: elements.prevShortcut.textContent,
    nextShortcut: elements.nextShortcut.textContent
  };
  
  try {
    await chrome.storage.sync.set(settings);
    
    const response = await chrome.runtime.sendMessage({
      action: 'saveSettings',
      data: settings
    });
    
    if (response.success) {
      showStatus('Settings saved successfully!', 'success');
      
      const tabs = await chrome.tabs.query({ url: '*://app.plex.tv/*' });
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, {
          action: 'updateSettings',
          settings: settings
        });
      });
    } else {
      showStatus('Failed to save settings: ' + response.error, 'error');
    }
  } catch (error) {
    console.error('Failed to save settings:', error);
    showStatus('Failed to save settings', 'error');
  }
}

function resetSettings() {
  if (confirm('Are you sure you want to reset all settings to defaults?')) {
    chrome.storage.sync.clear(() => {
      loadSettings();
      showStatus('Settings reset to defaults', 'success');
    });
  }
}

function showStatus(message, type) {
  elements.statusMessage.textContent = message;
  elements.statusMessage.className = `status-message ${type}`;
  elements.statusMessage.style.display = 'block';
  
  setTimeout(() => {
    elements.statusMessage.style.display = 'none';
  }, 3000);
}

function openShortcutModal(type) {
  currentShortcutEdit = type;
  pendingShortcut = null;
  elements.shortcutModal.style.display = 'flex';
  elements.shortcutDisplay.textContent = 'Waiting...';
  elements.shortcutSave.disabled = true;
  
  document.addEventListener('keydown', captureShortcut);
}

function closeShortcutModal() {
  elements.shortcutModal.style.display = 'none';
  currentShortcutEdit = null;
  pendingShortcut = null;
  document.removeEventListener('keydown', captureShortcut);
}

function captureShortcut(event) {
  event.preventDefault();
  event.stopPropagation();
  
  if (event.key === 'Escape') {
    closeShortcutModal();
    return;
  }
  
  const modifiers = [];
  if (event.ctrlKey) modifiers.push('Ctrl');
  if (event.altKey) modifiers.push('Alt');
  if (event.shiftKey) modifiers.push('Shift');
  if (event.metaKey) modifiers.push('Meta');
  
  if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key)) {
    elements.shortcutDisplay.textContent = modifiers.join('+') + '+...';
    return;
  }
  
  let key = event.key;
  if (key === ' ') key = 'Space';
  if (key.length === 1) key = key.toUpperCase();
  
  modifiers.push(key);
  pendingShortcut = modifiers.join('+');
  
  elements.shortcutDisplay.textContent = pendingShortcut;
  elements.shortcutSave.disabled = false;
}

function saveShortcut() {
  if (!pendingShortcut || !currentShortcutEdit) return;
  
  if (currentShortcutEdit === 'prev') {
    elements.prevShortcut.textContent = pendingShortcut;
  } else {
    elements.nextShortcut.textContent = pendingShortcut;
  }
  
  closeShortcutModal();
}

async function testConnection() {
  const apiUrl = elements.apiUrl.value || 'http://localhost:8002';
  const apiKey = elements.apiKey.value || 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6';
  
  elements.testConnectionBtn.disabled = true;
  elements.connectionStatus.textContent = 'Testing...';
  elements.connectionStatus.style.color = '#ffc107';
  
  try {
    const response = await chrome.runtime.sendMessage({
      action: 'updateApiKey',
      data: { apiUrl, apiKey }
    });
    
    if (response.success && response.connected) {
      elements.connectionStatus.textContent = '✓ Connected';
      elements.connectionStatus.style.color = '#4caf50';
    } else {
      elements.connectionStatus.textContent = '✗ Connection failed';
      elements.connectionStatus.style.color = '#f44336';
    }
  } catch (error) {
    elements.connectionStatus.textContent = '✗ Error: ' + error.message;
    elements.connectionStatus.style.color = '#f44336';
  } finally {
    elements.testConnectionBtn.disabled = false;
    
    // Clear status after 3 seconds
    setTimeout(() => {
      elements.connectionStatus.textContent = '';
    }, 3000);
  }
}

function setupEventListeners() {
  elements.saveBtn.addEventListener('click', saveSettings);
  elements.resetBtn.addEventListener('click', resetSettings);
  elements.testConnectionBtn.addEventListener('click', testConnection);
  
  elements.editPrevShortcut.addEventListener('click', () => openShortcutModal('prev'));
  elements.editNextShortcut.addEventListener('click', () => openShortcutModal('next'));
  
  elements.shortcutCancel.addEventListener('click', closeShortcutModal);
  elements.shortcutSave.addEventListener('click', saveShortcut);
  
  elements.shortcutModal.addEventListener('click', (event) => {
    if (event.target === elements.shortcutModal) {
      closeShortcutModal();
    }
  });
  
  elements.apiUrl.addEventListener('input', () => {
    const url = elements.apiUrl.value;
    if (url && !url.match(/^https?:\/\//)) {
      elements.apiUrl.setCustomValidity('Please enter a valid URL starting with http:// or https://');
    } else {
      elements.apiUrl.setCustomValidity('');
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  setupEventListeners();
});