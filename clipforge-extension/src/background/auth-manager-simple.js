import SimpleClipForgeAPI from './api-client-simple.js';

class SimpleAuthManager {
  constructor() {
    this.api = null;
  }

  async initialize() {
    const settings = await chrome.storage.sync.get(['apiUrl', 'apiKey']);
    
    if (settings.apiKey) {
      this.api = new SimpleClipForgeAPI(settings.apiUrl, settings.apiKey);
    } else {
      // Use default test API key if none configured
      this.api = new SimpleClipForgeAPI(
        settings.apiUrl || 'http://localhost:8002',
        'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
      );
    }
    
    return this.api;
  }

  async testConnection() {
    if (!this.api) {
      await this.initialize();
    }
    
    try {
      const isValid = await this.api.testConnection();
      if (isValid) {
        // Save the successful configuration
        const settings = await chrome.storage.sync.get(['apiUrl', 'apiKey']);
        await chrome.storage.local.set({
          isAuthenticated: true,
          apiUrl: settings.apiUrl || 'http://localhost:8002',
          apiKey: settings.apiKey || 'cf_test_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
        });
      }
      return isValid;
    } catch (error) {
      console.error('Connection test failed:', error);
      return false;
    }
  }

  async isAuthenticated() {
    const data = await chrome.storage.local.get(['isAuthenticated', 'apiKey']);
    
    // If we have an API key saved, test if it still works
    if (data.apiKey || data.isAuthenticated) {
      return await this.testConnection();
    }
    
    return false;
  }

  async getUserInfo() {
    if (!this.api) {
      await this.initialize();
    }
    
    try {
      return await this.api.getUserInfo();
    } catch (error) {
      console.error('Failed to get user info:', error);
      return null;
    }
  }

  async disconnect() {
    await chrome.storage.local.remove(['isAuthenticated', 'apiKey']);
    this.api = null;
  }

  async updateApiKey(apiUrl, apiKey) {
    // Save new credentials
    await chrome.storage.sync.set({ apiUrl, apiKey });
    await chrome.storage.local.set({ apiUrl, apiKey });
    
    // Reinitialize with new credentials
    this.api = new SimpleClipForgeAPI(apiUrl, apiKey);
    
    // Test the connection
    return await this.testConnection();
  }
}

export default SimpleAuthManager;