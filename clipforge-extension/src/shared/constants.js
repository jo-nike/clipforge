export const CONSTANTS = {
  API: {
    DEFAULT_BASE_URL: 'http://localhost:8000',
    ENDPOINTS: {
      AUTH_SIGNIN: '/api/v1/auth/signin',
      AUTH_PIN: '/api/v1/auth/pin',
      CLIPS_CREATE: '/api/v1/clips/create',
      CLIPS_RECENT: '/api/v1/clips/recent',
      SESSIONS_CURRENT: '/api/v1/sessions/current',
      USERS_ME: '/api/v1/users/me'
    },
    TIMEOUT: 30000,
    POLL_INTERVAL: 2000,
    MAX_POLL_ATTEMPTS: 60
  },
  
  PLEX: {
    DOMAINS: ['app.plex.tv', 'watch.plex.tv'],
    AUTH_URL: 'https://app.plex.tv/auth',
    CLIENT_ID: 'clipforge-extension',
    CLIENT_NAME: 'ClipForge Browser Extension'
  },
  
  DEFAULTS: {
    CLIP_DURATION: 30,
    AUTO_TITLE: true,
    NOTIFICATIONS: true,
    DEBUG_MODE: false,
    SHORTCUTS: {
      PREVIOUS: 'Alt+[',
      NEXT: 'Alt+]'
    }
  },
  
  STORAGE: {
    TOKEN_EXPIRY_DAYS: 7,
    SETTINGS_KEY: 'clipforge_settings',
    AUTH_KEY: 'clipforge_auth'
  },
  
  UI: {
    BUTTON_FEEDBACK_DURATION: 2000,
    NOTIFICATION_DURATION: 3000,
    PLAYER_DETECT_TIMEOUT: 30000,
    PLAYER_DETECT_INTERVAL: 500
  },
  
  MESSAGES: {
    NOT_AUTHENTICATED: 'Please connect to ClipForge first',
    CLIP_CREATED: 'Clip created successfully!',
    CLIP_FAILED: 'Failed to create clip',
    AUTH_SUCCESS: 'Connected to ClipForge',
    AUTH_FAILED: 'Authentication failed',
    SESSION_NOT_FOUND: 'Could not find Plex session',
    PLAYER_NOT_FOUND: 'Plex player not detected'
  }
};

export default CONSTANTS;