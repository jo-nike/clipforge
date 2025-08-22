import ClipForgeAPI from './api-client.js';

class AuthManager {
  constructor() {
    this.api = null;
    this.pollInterval = null;
  }

  async initialize() {
    const settings = await chrome.storage.sync.get(['apiUrl']);
    this.api = new ClipForgeAPI(settings.apiUrl);
    
    const tokens = await this.getStoredTokens();
    if (tokens.authToken && tokens.plexToken) {
      await this.api.setTokens(tokens.authToken, tokens.plexToken);
    }
    
    return this.api;
  }

  async initiateAuth() {
    try {
      const pinResponse = await this.api.createAuthPin();
      
      const authUrl = `https://app.plex.tv/auth#?clientID=clipforge-extension&code=${pinResponse.code}&context[device][product]=ClipForge`;
      
      const tab = await chrome.tabs.create({ url: authUrl });
      
      const token = await this.pollForToken(pinResponse.id);
      
      if (tab.id) {
        chrome.tabs.remove(tab.id);
      }
      
      const authResponse = await this.api.authenticate(token);
      
      await this.saveTokens(authResponse.access_token, token);
      
      return { success: true, user: authResponse.user };
    } catch (error) {
      console.error('Authentication failed:', error);
      throw error;
    }
  }

  async pollForToken(pinId, maxAttempts = 60) {
    return new Promise((resolve, reject) => {
      let attempts = 0;
      
      this.pollInterval = setInterval(async () => {
        attempts++;
        
        if (attempts > maxAttempts) {
          clearInterval(this.pollInterval);
          reject(new Error('Authentication timeout'));
          return;
        }
        
        try {
          const response = await this.api.checkAuthPin(pinId);
          
          if (response.auth_token) {
            clearInterval(this.pollInterval);
            resolve(response.auth_token);
          }
        } catch (error) {
          console.log('Pin not yet authorized, continuing to poll...');
        }
      }, 2000);
    });
  }

  async saveTokens(authToken, plexToken) {
    const tokenData = {
      authToken: authToken,
      plexToken: plexToken,
      tokenExpiry: Date.now() + (7 * 24 * 60 * 60 * 1000)
    };
    
    await chrome.storage.local.set(tokenData);
    await this.api.setTokens(authToken, plexToken);
  }

  async getStoredTokens() {
    const data = await chrome.storage.local.get(['authToken', 'plexToken', 'tokenExpiry']);
    
    if (data.tokenExpiry && data.tokenExpiry < Date.now()) {
      await this.refreshTokens();
      return this.getStoredTokens();
    }
    
    return data;
  }

  async refreshTokens() {
    try {
      const tokens = await chrome.storage.local.get(['plexToken']);
      
      if (!tokens.plexToken) {
        throw new Error('No Plex token available for refresh');
      }
      
      const response = await this.api.authenticate(tokens.plexToken);
      await this.saveTokens(response.access_token, tokens.plexToken);
      
      return response;
    } catch (error) {
      console.error('Token refresh failed:', error);
      await this.clearTokens();
      throw error;
    }
  }

  async clearTokens() {
    await chrome.storage.local.remove(['authToken', 'plexToken', 'tokenExpiry']);
    this.api.token = null;
    this.api.plexToken = null;
  }

  async isAuthenticated() {
    const tokens = await this.getStoredTokens();
    return !!(tokens.authToken && tokens.plexToken);
  }

  async getUserInfo() {
    try {
      const tokens = await this.getStoredTokens();
      
      if (!tokens.authToken) {
        return null;
      }
      
      return await this.api.getUserInfo();
    } catch (error) {
      console.error('Failed to get user info:', error);
      return null;
    }
  }
}

export default AuthManager;