// Plex OAuth implementation similar to Tautulli
let plexOAuthWindow = null;
let pinPolling = null;

const PLEX_OAUTH_URL = 'https://app.plex.tv/auth/';

// Popup loader HTML
const plexOAuthLoader = `
<style>
.login-loader-container {
    font-family: Arial, sans-serif;
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    background: #f5f5f5;
    display: flex;
    align-items: center;
    justify-content: center;
}
.login-loader-message {
    color: #333;
    text-align: center;
    font-size: 16px;
}
.spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #e5a00d;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
}
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>
<div class="login-loader-container">
    <div class="login-loader-message">
        <div class="spinner"></div>
        <strong>Plex Authentication</strong><br>
        Redirecting to the Plex login page...
    </div>
</div>`;

function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           ('ontouchstart' in window) ||
           (navigator.maxTouchPoints > 0);
}

function popupCenter(url, title, w, h) {
    // On mobile devices, return null to trigger redirect flow
    if (isMobileDevice()) {
        return null;
    }
    
    // Fixes dual-screen position
    const dualScreenLeft = window.screenLeft !== undefined ? window.screenLeft : window.screenX;
    const dualScreenTop = window.screenTop !== undefined ? window.screenTop : window.screenY;

    const width = window.innerWidth ? window.innerWidth : document.documentElement.clientWidth ? document.documentElement.clientWidth : screen.width;
    const height = window.innerHeight ? window.innerHeight : document.documentElement.clientHeight ? document.documentElement.clientHeight : screen.height;

    const left = ((width / 2) - (w / 2)) + dualScreenLeft;
    const top = ((height / 2) - (h / 2)) + dualScreenTop;
    
    return window.open(url, title, `scrollbars=yes, width=${w}, height=${h}, top=${top}, left=${left}`);
}

function closePlexOAuthWindow() {
    if (plexOAuthWindow) {
        plexOAuthWindow.close();
        plexOAuthWindow = null;
    }
    if (pinPolling) {
        clearInterval(pinPolling);
        pinPolling = null;
    }
}

async function createPlexPin() {
    try {
        const response = await fetch('/api/v1/auth/pin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            return await response.json();
        }
        throw new Error('Failed to create PIN');
    } catch (error) {
        return null;
    }
}

async function checkPinStatus(pinId) {
    try {
        const response = await fetch(`/api/v1/auth/pin/${pinId}`);
        if (response.ok) {
            return await response.json();
        }
        throw new Error('Failed to check PIN status');
    } catch (error) {
        return null;
    }
}

async function signInWithToken(token, rememberMe = false) {
    try {
        const response = await fetch('/api/v1/auth/signin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: token,
                remember_me: rememberMe
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            return { success: true, data: result };
        } else {
            return { success: false, error: result.detail || 'Authentication failed' };
        }
    } catch (error) {
        return { success: false, error: 'Network error' };
    }
}

function encodeOAuthParams(params) {
    return Object.keys(params).map(key => 
        [key, params[key]].map(encodeURIComponent).join("=")
    ).join("&");
}

async function plexOAuth(successCallback, errorCallback) {
    try {
        // Close any existing OAuth window
        closePlexOAuthWindow();
        
        // Create PIN
        const pinData = await createPlexPin();
        if (!pinData) {
            throw new Error('Failed to create authentication PIN');
        }
        
        // OAuth parameters - matching backend client ID
        const oauthParams = {
            'clientID': 'clipforge-v1',
            'context[device][product]': 'clipforge-v1',
            'context[device][version]': '1.0.0',
            'context[device][platform]': 'Web',
            'context[device][platformVersion]': '1.0',
            'context[device][device]': 'Browser',
            'context[device][deviceName]': 'ClipForge',
            'context[device][model]': 'Plex OAuth',
            'context[device][layout]': isMobileDevice() ? 'mobile' : 'desktop',
            'code': pinData.code
        };
        
        // Redirect to Plex OAuth
        const oauthUrl = PLEX_OAUTH_URL + '#!?' + encodeOAuthParams(oauthParams);
        
        // Try to create popup window
        plexOAuthWindow = popupCenter('', 'Plex-OAuth', 600, 700);
        
        if (!plexOAuthWindow) {
            // Mobile/popup blocked - use redirect flow
            // Store auth state in sessionStorage for return
            sessionStorage.setItem('plex_auth_pin_id', pinData.id);
            sessionStorage.setItem('plex_auth_redirect', 'true');
            
            // Redirect current window to Plex OAuth
            window.location.href = oauthUrl;
            return;
        }
        
        // Desktop popup flow
        // Show loading screen
        plexOAuthWindow.document.write(plexOAuthLoader);
        plexOAuthWindow.location = oauthUrl;
        
        // Start polling for authentication
        pinPolling = setInterval(async () => {
            // Check if popup is closed
            if (plexOAuthWindow.closed) {
                closePlexOAuthWindow();
                if (errorCallback) errorCallback('Authentication cancelled');
                return;
            }
            
            // Check PIN status
            const status = await checkPinStatus(pinData.id);
            if (status && status.authenticated && status.auth_token) {
                closePlexOAuthWindow();
                if (successCallback) successCallback(status.auth_token);
            }
        }, 1000);
        
        // Set timeout to close popup after 5 minutes
        setTimeout(() => {
            if (plexOAuthWindow && !plexOAuthWindow.closed) {
                closePlexOAuthWindow();
                if (errorCallback) errorCallback('Authentication timeout');
            }
        }, 5 * 60 * 1000);
        
    } catch (error) {
        closePlexOAuthWindow();
        if (errorCallback) errorCallback(error.message);
    }
}

// Export functions for global use
window.plexOAuth = plexOAuth;
window.signInWithToken = signInWithToken;
window.closePlexOAuthWindow = closePlexOAuthWindow;