import { CONSTANTS } from './constants.js';

class SecureStorage {
  constructor() {
    this.cache = new Map();
  }

  async get(keys) {
    if (typeof keys === 'string') {
      keys = [keys];
    }

    const cached = {};
    const uncached = [];

    for (const key of keys) {
      if (this.cache.has(key)) {
        cached[key] = this.cache.get(key);
      } else {
        uncached.push(key);
      }
    }

    if (uncached.length > 0) {
      const stored = await this.getFromStorage(uncached);
      Object.assign(cached, stored);
      
      for (const key in stored) {
        this.cache.set(key, stored[key]);
      }
    }

    return cached;
  }

  async set(data) {
    await this.setInStorage(data);
    
    for (const key in data) {
      this.cache.set(key, data[key]);
    }
  }

  async remove(keys) {
    if (typeof keys === 'string') {
      keys = [keys];
    }

    await this.removeFromStorage(keys);
    
    for (const key of keys) {
      this.cache.delete(key);
    }
  }

  async clear() {
    await this.clearStorage();
    this.cache.clear();
  }

  async saveTokens(authToken, plexToken) {
    const tokenData = {
      authToken: authToken,
      plexToken: plexToken,
      tokenExpiry: Date.now() + (CONSTANTS.STORAGE.TOKEN_EXPIRY_DAYS * 24 * 60 * 60 * 1000)
    };
    
    await this.set(tokenData);
  }

  async getTokens() {
    const data = await this.get(['authToken', 'plexToken', 'tokenExpiry']);
    
    if (data.tokenExpiry && data.tokenExpiry < Date.now()) {
      await this.remove(['authToken', 'plexToken', 'tokenExpiry']);
      return { authToken: null, plexToken: null };
    }
    
    return data;
  }

  async saveSettings(settings) {
    await chrome.storage.sync.set({ [CONSTANTS.STORAGE.SETTINGS_KEY]: settings });
  }

  async getSettings() {
    const result = await chrome.storage.sync.get(CONSTANTS.STORAGE.SETTINGS_KEY);
    return result[CONSTANTS.STORAGE.SETTINGS_KEY] || {};
  }

  async saveAuthData(authData) {
    await this.set({ [CONSTANTS.STORAGE.AUTH_KEY]: authData });
  }

  async getAuthData() {
    const result = await this.get(CONSTANTS.STORAGE.AUTH_KEY);
    return result[CONSTANTS.STORAGE.AUTH_KEY] || null;
  }

  async clearAuthData() {
    await this.remove([
      'authToken',
      'plexToken',
      'tokenExpiry',
      CONSTANTS.STORAGE.AUTH_KEY
    ]);
  }

  async getFromStorage(keys) {
    return new Promise((resolve) => {
      chrome.storage.local.get(keys, (result) => {
        if (chrome.runtime.lastError) {
          console.error('Storage get error:', chrome.runtime.lastError);
          resolve({});
        } else {
          resolve(result);
        }
      });
    });
  }

  async setInStorage(data) {
    return new Promise((resolve, reject) => {
      chrome.storage.local.set(data, () => {
        if (chrome.runtime.lastError) {
          console.error('Storage set error:', chrome.runtime.lastError);
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }

  async removeFromStorage(keys) {
    return new Promise((resolve, reject) => {
      chrome.storage.local.remove(keys, () => {
        if (chrome.runtime.lastError) {
          console.error('Storage remove error:', chrome.runtime.lastError);
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }

  async clearStorage() {
    return new Promise((resolve, reject) => {
      chrome.storage.local.clear(() => {
        if (chrome.runtime.lastError) {
          console.error('Storage clear error:', chrome.runtime.lastError);
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }

  async getSyncStorage(keys) {
    return new Promise((resolve) => {
      chrome.storage.sync.get(keys, (result) => {
        if (chrome.runtime.lastError) {
          console.error('Sync storage get error:', chrome.runtime.lastError);
          resolve({});
        } else {
          resolve(result);
        }
      });
    });
  }

  async setSyncStorage(data) {
    return new Promise((resolve, reject) => {
      chrome.storage.sync.set(data, () => {
        if (chrome.runtime.lastError) {
          console.error('Sync storage set error:', chrome.runtime.lastError);
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }
}

export default new SecureStorage();