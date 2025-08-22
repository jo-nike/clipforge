class SimpleClipForgeAPI {
  constructor(baseUrl, apiKey) {
    // Ensure baseUrl doesn't end with a slash
    this.baseUrl = (baseUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.apiKey = apiKey;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey,
      ...options.headers
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
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

  async testConnection() {
    // Test the API key by calling a simple endpoint
    try {
      await this.request('/api/v1/sessions/current', {
        method: 'GET'
      });
      return true;
    } catch (error) {
      return false;
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
    // With API key auth, we return a simple user object
    return {
      username: 'API User',
      email: 'api@clipforge.local',
      auth_method: 'api_key'
    };
  }
}

export default SimpleClipForgeAPI;