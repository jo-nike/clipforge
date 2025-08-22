class ClipForgeAPI {
  constructor(baseUrl) {
    // Ensure baseUrl doesn't end with a slash
    this.baseUrl = (baseUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.token = null;
    this.plexToken = null;
  }

  async setTokens(authToken, plexToken) {
    this.token = authToken;
    this.plexToken = plexToken;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      // Add origin header for CORS
      'Origin': chrome.runtime.getURL(''),
      ...options.headers
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        // Important: include credentials for CORS
        credentials: 'include',
        mode: 'cors'
      });

      if (!response.ok) {
        let errorDetail = `Request failed: ${response.status}`;
        try {
          const error = await response.json();
          errorDetail = error.detail || error.message || error.error || errorDetail;
          console.error('API Error Response:', error);
        } catch (e) {
          errorDetail = `${response.status} ${response.statusText}`;
        }
        throw new Error(errorDetail);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  async createQuickClip(sessionKey, startTime, endTime, title) {
    return this.request('/api/v1/clips/create', {
      method: 'POST',
      body: JSON.stringify({
        session_key: sessionKey,
        start_time: startTime,
        end_time: endTime,
        title: title,
        clip_type: 'quick'
      })
    });
  }

  async authenticate(plexToken) {
    const response = await this.request('/api/v1/auth/signin', {
      method: 'POST',
      body: JSON.stringify({
        plex_token: plexToken
      })
    });

    if (response.access_token) {
      this.token = response.access_token;
    }

    return response;
  }

  async createAuthPin() {
    // Note: This endpoint should be CSRF-exempt
    // Make request directly without credentials to avoid CSRF issues
    const url = `${this.baseUrl}/api/v1/auth/pin`;
    console.log('Creating auth PIN at:', url);
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          client_id: 'clipforge-extension',
          client_name: 'ClipForge Browser Extension'
        }),
        // No credentials to avoid CSRF token requirement
        credentials: 'omit',
        mode: 'cors'
      });

      if (!response.ok) {
        let errorDetail = `Request failed: ${response.status}`;
        try {
          const error = await response.json();
          errorDetail = error.detail || error.message || error.error || errorDetail;
          console.error('PIN creation error:', error);
        } catch (e) {
          errorDetail = `${response.status} ${response.statusText}`;
        }
        throw new Error(errorDetail);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to create auth PIN:', error);
      throw error;
    }
  }

  async checkAuthPin(pinId) {
    // Also make this request without credentials
    const url = `${this.baseUrl}/api/v1/auth/pin/${pinId}`;
    
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'omit',
        mode: 'cors'
      });

      if (!response.ok) {
        if (response.status === 404) {
          // PIN not ready yet, this is expected during polling
          return { auth_token: null };
        }
        throw new Error(`Request failed: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to check auth PIN:', error);
      throw error;
    }
  }

  async getCurrentSession() {
    return this.request('/api/v1/sessions/current', {
      method: 'GET'
    });
  }

  async getRecentClips(limit = 5) {
    return this.request(`/api/v1/clips/recent?limit=${limit}`, {
      method: 'GET'
    });
  }

  async getUserInfo() {
    return this.request('/api/v1/users/me', {
      method: 'GET'
    });
  }

  async refreshToken() {
    if (!this.plexToken) {
      throw new Error('No Plex token available for refresh');
    }

    return this.authenticate(this.plexToken);
  }
}

export default ClipForgeAPI;