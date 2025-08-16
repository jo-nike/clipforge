/**
 * Clippex v2 - Main Application JavaScript
 * Handles session management, clip creation, and video editing functionality
 */

// Global application state
let currentUser = null;
let currentSessionData = null;
let allUserSessions = null;
let currentPreviewFrames = null;

// Media token cache
let mediaTokenCache = new Map();

// Recently created clips cache (to help with error handling)
let recentlyCreatedClips = new Map();

// CSRF token management
let csrfToken = null;

// Bulk selection state
let bulkSelectMode = false;
let selectedClipIds = new Set();

// Pagination state
let currentPage = 1;
let clipsPerPage = 10;
let totalClips = 0;

// Video player references
let currentVideoUrl = '';
let currentClipId = '';
let videoPlayer = null;

// Video editor modal state
let editorModalPlayer = null;
let modalStartMarker = null;
let modalEndMarker = null;
let currentModalClipId = '';
let currentModalVideoUrl = '';
let currentModalVideoTitle = '';

// Frame selection state
let selectedFrames = new Set();
let allFrames = [];

// Confirmation modal callback
let confirmationCallback = null;

// Video.js fallback HTML constant
const VIDEO_JS_FALLBACK_HTML = `
    <p class="vjs-no-js">
        To view this video please enable JavaScript, and consider upgrading to a 
        <a href="https://videojs.com/html5-video-support/" target="_blank">web browser that 
        <span>supports HTML5 video</span></a>.
    </p>
`;

// Clip success modal state
let currentCreatedClipId = null;
let currentCreatedClipUrl = null;
let currentCreatedClipTitle = null;

/**
 * Authentication Functions
 */
async function getCurrentUser() {
    try {
        const response = await fetch('/api/v1/auth/me', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            return data.user;
        } else if (response.status === 401) {
            window.location.href = '/login';
            return null;
        } else {
            throw new Error('Failed to get user info');
        }
    } catch (error) {
        console.error('Error getting user:', error);
        return null;
    }
}

/**
 * Refresh the entire application
 */
function refreshApp() {
    window.location.reload();
}

async function logout() {
    try {
        const response = await safeFetch('/api/v1/auth/logout', {
            method: 'POST'
        });
        
        // Clear media token cache on logout for security
        clearMediaTokenCache();
        
        if (response.ok) {
            window.location.href = '/login';
        } else {
            showAlert('Logout failed', 'Error');
        }
    } catch (error) {
        console.error('Logout error:', error);
        clearMediaTokenCache(); // Clear cache even on error
        showAlert('Logout failed', 'Error');
    }
}

/**
 * CSRF Token Management Functions - Cookie-based approach
 */
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function updateCSRFToken(response) {
    // Update from header if available (immediate use)
    const token = response.headers.get('X-CSRF-Token');
    if (token) {
        csrfToken = token;
    }
}

function getCSRFHeaders() {
    // Always read fresh token from cookie
    const cookieToken = getCookie('csrf_token');
    if (cookieToken) {
        csrfToken = cookieToken;
        return { 'X-CSRF-Token': csrfToken };
    } else {
        return {};
    }
}

function ensureCSRFToken() {
    // No async needed - just read from cookie
    const cookieToken = getCookie('csrf_token');
    if (cookieToken) {
        csrfToken = cookieToken;
    } else {
    }
}

/**
 * Enhanced Fetch Function with CSRF Support
 * 
 * IMPORTANT: Use safeFetch() for ALL state-changing requests (POST, PUT, DELETE, PATCH)
 * Only use native fetch() for:
 * - GET requests (safe methods that don't need CSRF protection)  
 * - Auth endpoints that are exempt from CSRF (like /auth/pin, /auth/signin)
 */
async function safeFetch(url, options = {}) {
    // Add CSRF headers for state-changing requests
    if (options.method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method.toUpperCase())) {
        ensureCSRFToken(); // Synchronous now
        
        // Add CSRF headers
        options.headers = {
            ...options.headers,
            ...getCSRFHeaders()
        };
    }
    
    // Add credentials by default
    options.credentials = options.credentials || 'include';
    
    try {
        const response = await fetch(url, options);
        
        // Update CSRF token from response header if available
        updateCSRFToken(response);
        
        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

/**
 * Media Token Management Functions
 */
async function getMediaToken(resourceId, resourceType) {
    // Check cache first
    const cacheKey = `${resourceType}:${resourceId}`;
    const cached = mediaTokenCache.get(cacheKey);
    
    if (cached && cached.expiresAt > Date.now()) {
        return cached.token;
    }

    try {
        
        const response = await safeFetch('/api/v1/auth/media-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                resource_id: resourceId,
                resource_type: resourceType
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            
            // Cache the token (expires in 50 minutes to be safe)
            const expiresAt = Date.now() + (50 * 60 * 1000);
            mediaTokenCache.set(cacheKey, {
                token: data.token,
                expiresAt: expiresAt
            });
            
            return data.token;
        } else if (response.status === 401) {
            window.location.href = '/login';
            return null;
        } else {
            console.error('Failed to get media token:', response.statusText, 'Status:', response.status);
            const errorText = await response.text();
            console.error('Error response body:', errorText);
            return null;
        }
    } catch (error) {
        console.error('Error getting media token:', error);
        return null;
    }
}

function getMediaUrl(baseUrl, resourceId, resourceType, token = null, forDownload = false) {
    let url = baseUrl;
    const params = new URLSearchParams();
    
    if (token) {
        params.append('token', token);
    }
    
    if (forDownload) {
        params.append('download', 'true');
    }
    
    if (params.toString()) {
        const separator = baseUrl.includes('?') ? '&' : '?';
        url += separator + params.toString();
    }
    
    return url;
}

async function getSecureMediaUrl(baseUrl, resourceId, resourceType, forDownload = false) {
    
    const token = await getMediaToken(resourceId, resourceType);
    
    const finalUrl = getMediaUrl(baseUrl, resourceId, resourceType, token, forDownload);
    
    return finalUrl;
}

function clearMediaTokenCache() {
    mediaTokenCache.clear();
}

function markClipAsRecentlyCreated(clipId) {
    // Mark clip as recently created (expires in 5 minutes)
    const expiresAt = Date.now() + (5 * 60 * 1000);
    recentlyCreatedClips.set(clipId, expiresAt);
}

function isClipRecentlyCreated(clipId) {
    const expiresAt = recentlyCreatedClips.get(clipId);
    if (expiresAt && expiresAt > Date.now()) {
        return true;
    }
    // Clean up expired entries
    if (expiresAt) {
        recentlyCreatedClips.delete(clipId);
    }
    return false;
}

async function handleMediaError(error, resourceId, resourceType, retryFunction) {
    
    // Check if this looks like a 401/authentication error
    if (error && (error.code === 4 || error.message?.includes('401') || error.message?.includes('Unauthorized'))) {
        
        // Clear the specific token from cache
        const cacheKey = `${resourceType}:${resourceId}`;
        mediaTokenCache.delete(cacheKey);
        
        // Try to get a fresh token and retry
        const newToken = await getMediaToken(resourceId, resourceType);
        if (newToken && retryFunction) {
            return retryFunction(newToken);
        } else {
            console.error('Failed to get fresh token');
            showAlert('Session expired. Please refresh the page.', 'Error');
        }
    }
    
    return false; // Indicate retry failed
}

function setupVideoPlayerErrorHandling(player, resourceId, resourceType) {
    if (!player) return;
    
    player.on('error', async () => {
        const error = player.error();
        console.error('Video player error:', error);
        
        if (error && error.code === 4) { // MEDIA_ERR_SRC_NOT_SUPPORTED / Network error
            // Check if this is a recently created clip that might not be ready yet
            if (isClipRecentlyCreated(resourceId)) {
                // This is likely a video that's still processing, not a format error
                showAlert('Video is still processing. Please try again in a few moments.', 'Video Not Ready');
                
                // Auto-close modals after showing the message
                setTimeout(() => {
                    // Close video preview modal if open
                    const videoPreviewModal = document.getElementById('video-preview-modal');
                    if (videoPreviewModal && videoPreviewModal.style.display === 'flex') {
                        closeVideoPreview();
                    }
                    
                    // Close video editor modal if open
                    const videoEditorModal = document.getElementById('video-editor-modal');
                    if (videoEditorModal && videoEditorModal.style.display === 'flex') {
                        closeVideoEditorModal();
                    }
                }, 3000);
                return;
            }
            
            // Try to handle as authentication error for other cases
            const handled = await handleMediaError(error, resourceId, resourceType, async (newToken) => {
                // Get the current source
                const currentSrc = player.src();
                if (currentSrc && currentSrc.src) {
                    // Update the source with new token
                    const baseUrl = currentSrc.src.split('?')[0];
                    const newUrl = getMediaUrl(baseUrl, resourceId, resourceType, newToken);
                    
                    // Reset player and load with new URL
                    player.src({
                        type: currentSrc.type,
                        src: newUrl
                    });
                    
                    return true;
                }
                return false;
            });
            
            if (!handled) {
                showAlert('Failed to load video. Please refresh the page.', 'Error');
            }
        }
    });
}

/**
 * Session Management Functions
 */
async function getCurrentSession() {
    try {
        const response = await fetch('/api/v1/sessions/current', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            return data;
        } else {
            throw new Error('Failed to get current session');
        }
    } catch (error) {
        console.error('Error getting current session:', error);
        return null;
    }
}

async function getAllUserSessions() {
    try {
        const response = await fetch('/api/v1/sessions/all', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            return data;
        } else {
            throw new Error('Failed to get all user sessions');
        }
    } catch (error) {
        console.error('Error getting all user sessions:', error);
        return null;
    }
}

/**
 * Utility Functions
 */
function formatDuration(ms) {
    if (!ms) return 'Unknown';
    const seconds = Math.floor(ms / 1000);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }
}

function formatProgress(viewOffset, duration) {
    if (!duration || duration === 0) return 'Unknown';
    const percent = Math.round((viewOffset / duration) * 100);
    return `${percent}%`;
}

function formatFileSize(bytes) {
    if (!bytes) return 'Unknown';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    
    return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function millisecondsToTimeInputs(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    return {
        hours: hours.toString().padStart(2, '0'),
        minutes: minutes.toString().padStart(2, '0'),
        seconds: remainingSeconds.toString().padStart(2, '0')
    };
}

function setTimeInputs(elementPrefix, timeValues) {
    document.getElementById(`${elementPrefix}-hour`).value = timeValues.hours;
    document.getElementById(`${elementPrefix}-minute`).value = timeValues.minutes;
    document.getElementById(`${elementPrefix}-second`).value = timeValues.seconds;
}

function setupModalCloseHandler(modalId, closeFunction) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.onclick = function(e) {
            if (e.target === this) {
                closeFunction();
            }
        };
    }
}

function initializeVideoJSPlayer(elementId, videoUrl, resourceId, resourceType, options = {}) {
    try {
        const videoElement = document.getElementById(elementId);
        if (!videoElement) {
            throw new Error(`Video element with ID '${elementId}' not found`);
        }
        
        // Clean and prepare element
        videoElement.className = 'video-js vjs-default-skin';
        videoElement.innerHTML = VIDEO_JS_FALLBACK_HTML;
        videoElement.removeAttribute('data-vjs-player');
        videoElement.style.removeProperty('width');
        videoElement.style.removeProperty('height');
        
        // Default options
        const defaultOptions = {
            responsive: true,
            fluid: true,
            playbackRates: [0.5, 1, 1.25, 1.5, 2],
            controls: true,
            preload: 'auto',
            sources: [{
                type: 'video/mp4',
                src: videoUrl
            }]
        };
        
        // Merge with custom options
        const playerOptions = { ...defaultOptions, ...options };
        
        // Initialize player
        const player = videojs(videoElement, playerOptions);
        
        // Set up error handling with token refresh capability if resource info provided
        if (resourceId && resourceType) {
            setupVideoPlayerErrorHandling(player, resourceId, resourceType);
        } else {
            player.on('error', function() {
                console.error('Video.js error:', player.error());
            });
        }
        
        return player;
        
    } catch (error) {
        console.error('Error initializing Video.js player:', error);
        showAlert('Error loading video player: ' + error.message, 'Error');
        return null;
    }
}

function cleanupVideoJSPlayer(player, elementId) {
    // Dispose player if exists
    if (player) {
        try {
            player.dispose();
        } catch (error) {
            console.error('Error disposing video player:', error);
        }
    }
    
    // Clean up video element
    const videoElement = document.getElementById(elementId);
    if (videoElement) {
        videoElement.className = 'video-js vjs-default-skin';
        videoElement.innerHTML = VIDEO_JS_FALLBACK_HTML;
        videoElement.removeAttribute('data-vjs-player');
        videoElement.style.removeProperty('width');
        videoElement.style.removeProperty('height');
    }
    
    return null; // Return null to clear player variable
}

function handleApiError(error, response, defaultMessage) {
    if (response && response.status === 403) {
        return response.json().then(errorData => {
            if (errorData.detail && errorData.detail.includes('Video limit exceeded')) {
                return `❌ ${errorData.detail}`;
            } else {
                return `❌ Error: ${errorData.detail}`;
            }
        });
    } else if (response && !response.ok) {
        return response.json().then(errorData => {
            return `❌ Error: ${errorData.detail || defaultMessage}`;
        });
    } else {
        return Promise.resolve(`❌ Network error: ${error.message || defaultMessage}`);
    }
}

function showErrorWithFallback(message, title = 'Error') {
    if (typeof showAlert === 'function') {
        showAlert(message, title);
    } else {
        console.error(`${title}: ${message}`);
        alert(`${title}: ${message}`);
    }
}

function setElementContent(elementId, content) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = content;
    }
}

function setElementDisplay(elementId, displayValue) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = displayValue;
    }
}

function setButtonState(buttonId, disabled, text) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = disabled;
        if (text) {
            button.textContent = text;
        }
    }
}

async function fetchSecureMediaUrlWithErrorHandling(baseUrl, resourceId, resourceType, forDownload = false) {
    try {
        const secureUrl = await getSecureMediaUrl(baseUrl, resourceId, resourceType, forDownload);
        if (!secureUrl) {
            showAlert('Failed to get secure media URL. Please try again.', 'Error');
            return null;
        }
        return secureUrl;
    } catch (error) {
        console.error('Error getting secure media URL:', error);
        showAlert('Failed to load media. Please try again.', 'Error');
        return null;
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const button = event.target;
        const originalText = button.textContent;
        button.textContent = '✅';
        button.style.color = 'green';
        
        setTimeout(() => {
            button.textContent = originalText;
            button.style.color = '';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy to clipboard:', err);
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            const button = event.target;
            const originalText = button.textContent;
            button.textContent = '✅';
            button.style.color = 'green';
            
            setTimeout(() => {
                button.textContent = originalText;
                button.style.color = '';
            }, 2000);
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        document.body.removeChild(textArea);
    });
}

/**
 * Download Helper Functions
 */
async function downloadMedia(resourceId, downloadUrl, filename, resourceType) {
    try {
        // Get secure URL with token for download
        const secureUrl = await getSecureMediaUrl(downloadUrl, resourceId, resourceType, true);
        if (!secureUrl) {
            showAlert('Failed to get download link. Please try again.', 'Error');
            return;
        }
        
        // Create temporary download link
        const link = document.createElement('a');
        link.href = secureUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
    } catch (error) {
        console.error(`Error downloading ${resourceType}:`, error);
        showAlert(`Failed to download ${resourceType}. Please try again.`, 'Error');
    }
}

/**
 * Input Helper Functions
 */
function getTimeInputValues() {
    const startHour = parseInt(document.getElementById('start-hour').value) || 0;
    const startMinute = parseInt(document.getElementById('start-minute').value) || 0;
    const startSecond = parseInt(document.getElementById('start-second').value) || 0;
    
    const endHour = parseInt(document.getElementById('end-hour').value) || 0;
    const endMinute = parseInt(document.getElementById('end-minute').value) || 0;
    const endSecond = parseInt(document.getElementById('end-second').value) || 0;
    
    return {
        start: { hour: startHour, minute: startMinute, second: startSecond },
        end: { hour: endHour, minute: endMinute, second: endSecond }
    };
}

/**
 * Session Display Functions
 */
function displayAllUserSessions(sessionData) {
    const sessionContent = document.getElementById('session-content');
    
    
    if (!sessionData.has_sessions || !sessionData.sessions || sessionData.sessions.length === 0) {
        sessionContent.innerHTML = `
            <div class="no-session">
                <div class="no-session-icon">📺</div>
                <h3>No Active Sessions</h3>
                <p>${sessionData.message || 'You are not currently watching anything on Plex.'}</p>
                <button id="retry-session-btn" class="btn btn-primary" onclick="loadCurrentSession()">🔄 Check Again</button>
            </div>
        `;
        return;
    }

    currentSessionData = null;
    const sessions = sessionData.sessions;
    
    let sessionsHtml = '<div class="sessions-container">';
    
    sessions.forEach((session, index) => {
        const media = session.media;
        const sessionInfo = session.session;
        
        if (!sessionInfo) {
            console.error('Session info is missing for session', index);
            return;
        }
        
        let mediaTitle = media.title;
        if (media.show_title) {
            mediaTitle = `${media.show_title} - ${media.title}`;
            if (media.season_number && media.episode_number) {
                mediaTitle = `${media.show_title} S${media.season_number}E${media.episode_number} - ${media.title}`;
            }
        }

        const progressPercent = sessionInfo.progress_percent || 0;
        const state = sessionInfo.state || 'unknown';
        const viewOffset = sessionInfo.view_offset || 0;
        
        sessionsHtml += `
            <div class="session-card ${index === 0 ? 'selected-session' : ''}" data-session-index="${index}">
                <div class="session-header-compact" onclick="selectSession(${index})">
                    <div class="session-selector">
                        <input type="radio" name="selected-session" value="${index}" ${index === 0 ? 'checked' : ''} 
                               onchange="selectSession(${index})" id="session-${index}" onclick="event.stopPropagation()">
                        <div class="session-labels" onclick="event.stopPropagation()">
                            <label for="session-${index}" class="session-select-label">
                                ${index === 0 ? '🎯 Selected' : '📱 Available'}
                            </label>
                            <span class="state-indicator-small state-${state}">
                                ${state === 'playing' ? '▶️' : state === 'paused' ? '⏸️' : '⏹️'}
                                ${state.charAt(0).toUpperCase() + state.slice(1)}
                            </span>
                        </div>
                    </div>
                    
                    <div class="session-summary">
                        <div class="media-icon">${media.media_type === 'episode' ? '📺' : media.media_type === 'movie' ? '🎬' : '🎵'}</div>
                        <div class="session-title-compact">
                            <h3 class="media-title-compact">${mediaTitle}</h3>
                            <div class="progress-info-compact">
                                <div class="progress-bar-container">
                                    <div class="progress-bar">
                                        <div class="progress-fill" style="width: ${progressPercent}%"></div>
                                    </div>
                                </div>
                                <div class="progress-text-compact">
                                    <span>${formatDuration(viewOffset)} / ${formatDuration(media.duration)}</span>
                                    <span>${formatProgress(viewOffset, media.duration)}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
    
    sessionsHtml += '</div>';
    sessionContent.innerHTML = sessionsHtml;
    
    allUserSessions = sessions;
    if (sessions.length > 0) {
        currentSessionData = { has_session: true, session: sessions[0] };
    }
    
    document.getElementById('clip-creation-section').style.display = 'block';
    document.getElementById('clips-gallery-section').style.display = 'block';
    
    setStartTimeToCurrentSession();
    loadUserClips();
}

function selectSession(index) {
    if (!allUserSessions || index >= allUserSessions.length) {
        console.error('Invalid session index:', index);
        return;
    }
    
    currentSessionData = { has_session: true, session: allUserSessions[index] };
    
    document.querySelectorAll('input[name="selected-session"]').forEach((radio, i) => {
        radio.checked = (i === index);
    });
    
    document.querySelectorAll('.session-card').forEach((card, i) => {
        if (i === index) {
            card.classList.add('selected-session');
        } else {
            card.classList.remove('selected-session');
        }
    });
    
    document.querySelectorAll('.session-select-label').forEach((label, i) => {
        label.textContent = i === index ? '🎯 Selected' : '📱 Available';
    });
    
    setStartTimeToCurrentSession();
}

async function loadCurrentSession() {
    const sessionContent = document.getElementById('session-content');
    const refreshBtn = document.getElementById('refresh-session-btn');
    
    sessionContent.innerHTML = `
        <div class="session-loading">
            <div class="spinner"></div>
            <p>Loading your active sessions...</p>
        </div>
    `;
    
    refreshBtn.disabled = true;
    refreshBtn.textContent = '🔄 Loading...';
    
    try {
        const sessionData = await getAllUserSessions();
        if (sessionData) {
            displayAllUserSessions(sessionData);
        } else {
            sessionContent.innerHTML = `
                <div class="session-error">
                    <h3>❌ Error Loading Sessions</h3>
                    <p>Unable to retrieve your active playback sessions.</p>
                    <button class="btn btn-primary" onclick="loadCurrentSession()">🔄 Try Again</button>
                </div>
            `;
        }
    } catch (error) {
        sessionContent.innerHTML = `
            <div class="session-error">
                <h3>❌ Connection Error</h3>
                <p>Failed to connect to the server.</p>
                <button class="btn btn-primary" onclick="loadCurrentSession()">🔄 Try Again</button>
            </div>
        `;
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = '🔄 Refresh';
    }
}

/**
 * UI State Functions
 */
function displayUserInfo(user) {
    document.getElementById('user-name').textContent = user.username;
    document.getElementById('user-info').style.display = 'flex';
}

function showError() {
    document.getElementById('loading-container').style.display = 'none';
    document.getElementById('error-container').style.display = 'block';
}

function showDashboard() {
    document.getElementById('loading-container').style.display = 'none';
    document.getElementById('dashboard-content').style.display = 'block';
}

/**
 * Time Input Functions
 */
function clearStartTime() {
    document.getElementById('start-hour').value = '';
    document.getElementById('start-minute').value = '';
    document.getElementById('start-second').value = '';
}

function clearEndTime() {
    document.getElementById('end-hour').value = '';
    document.getElementById('end-minute').value = '';
    document.getElementById('end-second').value = '';
}

function resetTimeInputs() {
    clearStartTime();
    clearEndTime();
    cleanupPreviewFrames();
}

function useCurrentTimeAsStart() {
    if (!currentSessionData || !currentSessionData.has_session) {
        showAlert('No active session to get current time from', 'Warning');
        return;
    }

    const session = currentSessionData.session;
    const viewOffset = session.session.view_offset || 0;
    const timeValues = millisecondsToTimeInputs(viewOffset);
    setTimeInputs('start', timeValues);
}

function useCurrentTimeAsEnd() {
    if (!currentSessionData || !currentSessionData.has_session) {
        showAlert('No active session to get current time from', 'Warning');
        return;
    }

    const session = currentSessionData.session;
    const viewOffset = session.session.view_offset || 0;
    const timeValues = millisecondsToTimeInputs(viewOffset);
    setTimeInputs('end', timeValues);
}

function setStartTimeToCurrentSession() {
    if (!currentSessionData || !currentSessionData.has_session) {
        return;
    }

    const session = currentSessionData.session;
    const viewOffset = session.session.view_offset || 0;
    const timeValues = millisecondsToTimeInputs(viewOffset);
    setTimeInputs('start', timeValues);
}

function addDuration(durationSeconds) {
    const timeInputs = getTimeInputValues();
    const { hour: startHour, minute: startMinute, second: startSecond } = timeInputs.start;

    if (startHour === 0 && startMinute === 0 && startSecond === 0) {
        showAlert('Please set a start time first', 'Warning');
        return;
    }

    const totalStartSeconds = startHour * 3600 + startMinute * 60 + startSecond;
    const totalEndSeconds = totalStartSeconds + durationSeconds;

    const endHours = Math.floor(totalEndSeconds / 3600);
    const endMinutes = Math.floor((totalEndSeconds % 3600) / 60);
    const endSecondsRem = totalEndSeconds % 60;

    document.getElementById('end-hour').value = endHours.toString().padStart(2, '0');
    document.getElementById('end-minute').value = endMinutes.toString().padStart(2, '0');
    document.getElementById('end-second').value = endSecondsRem.toString().padStart(2, '0');
}

function formatTimeString(hour, minute, second) {
    const h = hour.toString().padStart(2, '0');
    const m = minute.toString().padStart(2, '0');
    const s = second.toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

/**
 * Status Display Functions
 */
function showCreationStatus(message, type = 'info') {
    const statusDiv = document.getElementById('creation-status');
    statusDiv.className = `creation-status ${type}`;
    statusDiv.innerHTML = message;
    statusDiv.style.display = 'block';
}

function hideCreationStatus() {
    document.getElementById('creation-status').style.display = 'none';
}

/**
 * Clip Creation Functions
 */
async function createClip() {
    const timeInputs = getTimeInputValues();
    const { hour: startHour, minute: startMinute, second: startSecond } = timeInputs.start;
    const { hour: endHour, minute: endMinute, second: endSecondVal } = timeInputs.end;

    if (startHour === 0 && startMinute === 0 && startSecond === 0) {
        showAlert('Please enter a start time', 'Warning');
        return;
    }

    if (endHour === 0 && endMinute === 0 && endSecondVal === 0) {
        showAlert('Please enter an end time', 'Warning');
        return;
    }

    const startTime = formatTimeString(startHour, startMinute, startSecond);
    const endTime = formatTimeString(endHour, endMinute, endSecondVal);
    const quality = document.getElementById('clip-quality').value;
    const format = document.getElementById('clip-format').value;

    const clipRequest = {
        start_time: startTime,
        end_time: endTime,
        quality: quality,
        format: format,
        include_metadata: true
    };

    // Include session_key if a specific session is selected
    if (currentSessionData && currentSessionData.session && currentSessionData.session.session_key) {
        clipRequest.session_key = currentSessionData.session.session_key;
    }

    try {
        showCreationStatus('🎬 Creating your clip... This may take a few moments.', 'loading');
        
        const response = await safeFetch('/api/v1/clips/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(clipRequest)
        });

        if (response.ok) {
            const result = await response.json();
            if (result.status === 'completed') {
                hideCreationStatus();
                await cleanupPreviewFrames();
                resetTimeInputs();
                
                const clipData = {
                    clip_id: result.clip_id,
                    download_url: result.download_url,
                    duration: result.duration,
                    format: format,
                    quality: quality,
                    filename: result.filename,
                    title: currentSessionData?.session?.media?.title || 'New Clip'
                };
                
                // Mark this clip as recently created for better error handling
                markClipAsRecentlyCreated(result.clip_id);
                
                await showClipSuccessModal(clipData);
                
                // Delay refreshes to avoid interfering with video player initialization
                setTimeout(() => {
                    loadUserClips();
                    loadCurrentSession();
                }, 1000);
            } else if (result.status === 'failed') {
                showCreationStatus(`❌ Clip creation failed: ${result.error_message}`, 'error');
            } else {
                showCreationStatus(`⏳ Clip is being processed... (${result.status})`, 'info');
            }
        } else if (response.status === 403) {
            const error = await response.json();
            if (error.detail && error.detail.includes('Video limit exceeded')) {
                showCreationStatus(`❌ ${error.detail}`, 'error');
            } else {
                showCreationStatus(`❌ Error: ${error.detail}`, 'error');
            }
        } else {
            const error = await response.json();
            showCreationStatus(`❌ Error: ${error.detail}`, 'error');
        }
    } catch (error) {
        showCreationStatus(`❌ Network error: ${error.message}`, 'error');
    }
}

/**
 * Snapshot Functions
 */
async function createSnapshot() {
    const timeInputs = getTimeInputValues();
    const { hour: startHour, minute: startMinute, second: startSecond } = timeInputs.start;

    if (startHour === 0 && startMinute === 0 && startSecond === 0) {
        showCreationStatus('❌ Please set a timestamp first', 'error');
        return;
    }

    const timestamp = formatTimeString(startHour, startMinute, startSecond);
    
    try {
        const snapshotBtn = document.getElementById('create-snapshot-btn');
        snapshotBtn.disabled = true;
        snapshotBtn.textContent = '⏳ Extracting Frames...';
        
        showCreationStatus('📸 Extracting 25 frames around selected time...', 'loading');
        
        const response = await safeFetch('/api/v1/sessions/snapshots/multi-frame', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                center_timestamp: timestamp,
                frame_count_before: 12,
                frame_count_after: 12,
                format: 'jpg',
                quality: 'high',
                frame_interval: 0.5,
                ...(currentSessionData && currentSessionData.session && currentSessionData.session.session_key && {
                    session_key: currentSessionData.session.session_key
                })
            })
        });
        
        const result = await response.json();
        
        if (response.ok && result.status === 'completed') {
            showFrameSelectionModal(result);
            showCreationStatus('✅ Frames extracted! Select frames to download.', 'success');
        } else {
            throw new Error(result.error_message || 'Frame extraction failed');
        }
        
    } catch (error) {
        console.error('Error taking snapshot:', error);
        showCreationStatus(`❌ Failed to extract frames: ${error.message}`, 'error');
    } finally {
        const snapshotBtn = document.getElementById('create-snapshot-btn');
        if (snapshotBtn) {
            snapshotBtn.disabled = false;
            snapshotBtn.textContent = '📸 Take Snapshot';
        }
    }
}

/**
 * Frame Selection Functions
 */
function showFrameSelectionModal(frameData) {
    allFrames = frameData.frames;
    selectedFrames.clear();
    
    const frameGrid = document.getElementById('frame-grid');
    frameGrid.innerHTML = '';
    
    frameData.frames.forEach((frame, index) => {
        const frameElement = document.createElement('div');
        frameElement.className = 'frame-item';
        frameElement.dataset.frameId = frame.frame_id;
        
        if (frame.frame_id === frameData.center_frame_id) {
            frameElement.classList.add('center-frame');
        }
        
        // Get secure URL for snapshot image
        const snapshotId = frame.frame_id;
        getSecureMediaUrl(frame.download_url, snapshotId, 'snapshot').then(secureUrl => {
            frameElement.innerHTML = `
                <img src="${secureUrl || frame.download_url}" alt="Frame ${index + 1}" class="frame-image" loading="lazy">
                <div class="frame-info">
                    <div class="frame-timestamp">${frame.timestamp}</div>
                    <div class="frame-label">${frame.frame_id === frameData.center_frame_id ? 'Selected Time' : `Frame ${index + 1}`}</div>
                </div>
                <div class="frame-selection-overlay">✓</div>
            `;
        }).catch(error => {
            console.error('Error getting secure snapshot URL:', error);
            // Fallback to original URL (will likely fail with 401 but better than nothing)
            frameElement.innerHTML = `
                <img src="${frame.download_url}" alt="Frame ${index + 1}" class="frame-image" loading="lazy">
                <div class="frame-info">
                    <div class="frame-timestamp">${frame.timestamp}</div>
                    <div class="frame-label">${frame.frame_id === frameData.center_frame_id ? 'Selected Time' : `Frame ${index + 1}`}</div>
                </div>
                <div class="frame-selection-overlay">✓</div>
            `;
        });
        
        frameElement.addEventListener('click', () => toggleFrameSelection(frame.frame_id));
        frameGrid.appendChild(frameElement);
    });
    
    updateSelectionCount();
    document.getElementById('frame-selection-modal').style.display = 'flex';
}

function toggleFrameSelection(frameId) {
    const frameElement = document.querySelector(`[data-frame-id="${frameId}"]`);
    
    if (selectedFrames.has(frameId)) {
        selectedFrames.delete(frameId);
        frameElement.classList.remove('selected');
    } else {
        selectedFrames.add(frameId);
        frameElement.classList.add('selected');
    }
    
    updateSelectionCount();
}

function selectAllFrames() {
    allFrames.forEach(frame => {
        selectedFrames.add(frame.frame_id);
        const frameElement = document.querySelector(`[data-frame-id="${frame.frame_id}"]`);
        if (frameElement) {
            frameElement.classList.add('selected');
        }
    });
    updateSelectionCount();
}

function clearFrameSelection() {
    selectedFrames.clear();
    document.querySelectorAll('.frame-item').forEach(element => {
        element.classList.remove('selected');
    });
    updateSelectionCount();
}

function updateSelectionCount() {
    document.getElementById('selected-count').textContent = selectedFrames.size;
    const downloadBtn = document.getElementById('download-frames-btn');
    downloadBtn.disabled = selectedFrames.size === 0;
}

async function downloadSelectedFrames() {
    if (selectedFrames.size === 0) {
        alert('Please select at least one frame to download');
        return;
    }
    
    const selectedFrameData = allFrames.filter(frame => selectedFrames.has(frame.frame_id));
    
    for (const frame of selectedFrameData) {
        try {
            // Get secure URL for download
            const secureUrl = await getSecureMediaUrl(frame.download_url, frame.frame_id, 'snapshot');
            
            const link = document.createElement('a');
            link.href = secureUrl || frame.download_url;
            link.download = `frame_${frame.timestamp.replace(/:/g, '-')}.jpg`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            await new Promise(resolve => setTimeout(resolve, 200));
        } catch (error) {
            console.error('Error downloading frame:', frame.frame_id, error);
        }
    }
    
    closeFrameSelectionModal();
    showCreationStatus(`✅ Started downloading ${selectedFrames.size} frame(s)`, 'success');
}

async function closeFrameSelectionModal() {
    document.getElementById('frame-selection-modal').style.display = 'none';
    
    // Delete the screenshots from the server
    if (allFrames && allFrames.length > 0) {
        try {
            const frameIds = allFrames.map(frame => frame.frame_id);
            const response = await safeFetch('/api/v1/sessions/snapshots/cleanup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ frame_ids: frameIds })
            });
            
            if (!response.ok) {
            }
        } catch (error) {
        }
    }
    
    selectedFrames.clear();
    allFrames = [];
}

/**
 * Clips Management Functions
 */
async function loadUserClips(page = currentPage, pageSize = clipsPerPage) {
    const clipsList = document.getElementById('clips-list');
    
    try {
        clipsList.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading your clips...</p>
            </div>
        `;

        const response = await fetch(`/api/v1/clips/list?page=${page}&page_size=${pageSize}`, {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            currentPage = data.page || page;
            clipsPerPage = data.page_size || pageSize;
            totalClips = data.total_count || data.clips.length;
            
            displayClips(data.clips);
            updatePaginationControls(data);
        } else {
            clipsList.innerHTML = `
                <div class="error">
                    <p>❌ Failed to load clips</p>
                    <button class="btn btn-primary" onclick="loadUserClips()">🔄 Try Again</button>
                </div>
            `;
        }
    } catch (error) {
        clipsList.innerHTML = `
            <div class="error">
                <p>❌ Network error loading clips</p>
                <button class="btn btn-primary" onclick="loadUserClips()">🔄 Try Again</button>
            </div>
        `;
    }
}

async function displayClips(clips) {
    const clipsList = document.getElementById('clips-list');
    
    if (clips.length === 0) {
        clipsList.innerHTML = `
            <div class="no-clips">
                <div class="no-clips-icon">🎬</div>
                <h3>No clips yet</h3>
                <p>Create your first clip from the current session above!</p>
            </div>
        `;
        return;
    }

    const clipsWithEdits = await Promise.all(clips.map(async (clip) => {
        try {
            const response = await fetch(`/api/v1/clips/${clip.clip_id}/edited`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                clip.edited_videos = data.edited_videos || [];
            } else {
                clip.edited_videos = [];
            }
        } catch (error) {
            console.error('Failed to load edited videos for clip:', clip.clip_id, error);
            clip.edited_videos = [];
        }
        return clip;
    }));

    const clipsHtml = clipsWithEdits.map(clip => {
        const metadata = clip.metadata;
        const createdAt = metadata ? new Date(metadata.created_at).toLocaleString() : 'Unknown';
        const title = metadata ? metadata.title : 'Unknown';
        const showInfo = metadata && metadata.show_name ? 
            `${metadata.show_name} S${metadata.season_number}E${metadata.episode_number}` : '';

        const editedVideosHtml = `
            <div class="edited-videos">
                ${clip.edited_videos.length > 0 ? `
                    <div class="edited-videos-header" onclick="toggleEditedVideos('${clip.clip_id}')" style="cursor: pointer;">
                        <span>📝 Subclips (${clip.edited_videos.length})</span>
                        <span id="toggle-${clip.clip_id}">▼</span>
                    </div>
                    <div class="edited-videos-list" id="edited-${clip.clip_id}" style="display: none;">
                        ${clip.edited_videos.map(edit => `
                            <div class="edited-video-item">
                                <div class="edited-info">
                                    <span class="edited-duration">${edit.duration ? Math.round(edit.duration) + 's' : ''}</span>
                                    <span class="edited-size">${formatFileSize(edit.file_size)}</span>
                                    <span class="edited-date">${new Date(edit.created_at).toLocaleString()}</span>
                                </div>
                                <div class="edited-actions">
                                    <button class="btn btn-small btn-secondary" onclick="previewSubclip('${edit.download_url.replace(/'/g, "\\'")}', 'Subclip from ${title.replace(/'/g, "\\'")}')">📽️</button>
                                    <button class="btn btn-small btn-primary" onclick="downloadSubclip('${edit.edit_id}', '${edit.download_url.replace(/'/g, "\\'")}', '${edit.filename || 'subclip.mp4'}')">📥</button>
                                    <button class="btn btn-small btn-danger" onclick="deleteEditedVideo('${edit.edit_id}', '${clip.clip_id}')">🗑️</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;

        const safeTitle = title.replace(/'/g, "\\'").replace(/"/g, '\\"');
        const safeDownloadUrl = clip.download_url.replace(/'/g, "\\'").replace(/"/g, '\\"');
        const safeClipId = clip.clip_id.replace(/'/g, "\\'").replace(/"/g, '\\"');

        return `
            <div class="clip-item" data-clip-id="${clip.clip_id}" onclick="handleClipClick(event, '${clip.clip_id}')">
                <div class="clip-thumbnail-container">
                    ${clip.thumbnail_url ? `<img class="clip-thumbnail" src="" data-thumbnail-url="${clip.thumbnail_url}" data-clip-id="${clip.clip_id}" alt="Video thumbnail" onerror="this.style.display='none'">` : ''}
                </div>
                <div class="clip-info">
                    <div class="clip-title-container">
                        <div class="clip-title" id="clip-title-${clip.clip_id}" ondblclick="event.stopPropagation(); startRenaming('${clip.clip_id}', '${safeTitle}')" title="Double-click to rename">${title}</div>
                        <input type="text" class="clip-title-input" id="clip-title-input-${clip.clip_id}" value="${title}" style="display: none;" onblur="cancelRenaming('${clip.clip_id}', '${safeTitle}')" onkeydown="handleRenameKeydown(event, '${clip.clip_id}', '${safeTitle}')">
                    </div>
                    ${showInfo ? `<div class="clip-show">${showInfo}</div>` : ''}
                    <div class="clip-meta">
                        <span class="clip-duration">${clip.duration ? Math.round(clip.duration) + 's' : ''}</span>
                        <span class="clip-size">${formatFileSize(clip.file_size)}</span>
                        <span class="clip-date">${createdAt}</span>
                    </div>
                    ${metadata && metadata.original_timestamp ? 
                        `<div class="clip-original-time">From: ${metadata.original_timestamp}</div>` : ''}
                </div>
                <div class="clip-actions">
                    <button class="btn btn-secondary" onclick="event.stopPropagation(); previewClip('${safeDownloadUrl}', '${safeTitle}', '${safeClipId}')">👁️ Preview</button>
                    <button class="btn btn-primary" onclick="event.stopPropagation(); editClip('${safeClipId}', '${safeDownloadUrl}', '${safeTitle}')">✂️ Edit</button>
                    <button class="btn btn-primary" onclick="event.stopPropagation(); downloadClip('${safeClipId}', '${safeDownloadUrl}', '${clip.filename || 'clip.mp4'}')">📥 Download</button>
                    <button class="btn btn-danger" onclick="event.stopPropagation(); deleteClip('${clip.clip_id}')">🗑️ Delete</button>
                </div>
                ${editedVideosHtml}
            </div>
        `;
    }).join('');

    clipsList.innerHTML = clipsHtml;
    
    // Load secure thumbnail URLs for clips that have thumbnails
    loadThumbnails();
    
    if (clips.length === 0) {
        bulkSelectMode = false;
    }
    updateBulkSelectUI();
}

/**
 * Load secure thumbnail URLs for all thumbnail images
 */
async function loadThumbnails() {
    const thumbnailImages = document.querySelectorAll('.clip-thumbnail');
    
    for (const img of thumbnailImages) {
        const thumbnailUrl = img.getAttribute('data-thumbnail-url');
        const clipId = img.getAttribute('data-clip-id');
        
        if (thumbnailUrl && clipId) {
            try {
                const secureUrl = await getSecureMediaUrl(thumbnailUrl, clipId, 'thumbnail');
                if (secureUrl) {
                    img.src = secureUrl;
                    img.style.display = 'block';
                }
            } catch (error) {
                console.log(`Failed to load thumbnail for clip ${clipId}:`, error);
                // Thumbnail fails silently - don't show anything
                img.style.display = 'none';
            }
        }
    }
}

/**
 * Pagination Functions
 */
function updatePaginationControls(data) {
    const paginationDiv = document.getElementById('clips-pagination');
    const clipsList = document.getElementById('clips-list');
    
    // Show pagination only if there are clips
    if (data.clips && data.clips.length > 0) {
        paginationDiv.style.display = 'block';
        
        // Update pagination info
        const totalPages = Math.ceil(totalClips / clipsPerPage);
        const startIndex = (currentPage - 1) * clipsPerPage + 1;
        const endIndex = Math.min(currentPage * clipsPerPage, totalClips);
        
        // Update pagination info with proper spacing
        const paginationInfo = document.querySelector('.pagination-info');
        if (totalClips > 0) {
            paginationInfo.innerHTML = `${startIndex}-${endIndex} of ${totalClips} clips`;
        } else {
            paginationInfo.innerHTML = `0 of 0 clips`;
        }
        document.getElementById('current-page').textContent = currentPage;
        document.getElementById('total-pages').textContent = totalPages;
        
        // Update button states
        const prevBtn = document.getElementById('prev-page-btn');
        const nextBtn = document.getElementById('next-page-btn');
        
        prevBtn.disabled = currentPage <= 1;
        nextBtn.disabled = currentPage >= totalPages;
        
        // Update page size selector
        document.getElementById('clips-per-page').value = clipsPerPage;
    } else {
        paginationDiv.style.display = 'none';
    }
}

function goToPage(page) {
    if (page >= 1 && page <= Math.ceil(totalClips / clipsPerPage)) {
        loadUserClips(page, clipsPerPage);
    }
}

function changePageSize() {
    const newPageSize = parseInt(document.getElementById('clips-per-page').value);
    currentPage = 1; // Reset to first page when changing page size
    loadUserClips(1, newPageSize);
}

function goToPreviousPage() {
    if (currentPage > 1) {
        goToPage(currentPage - 1);
    }
}

function goToNextPage() {
    const totalPages = Math.ceil(totalClips / clipsPerPage);
    if (currentPage < totalPages) {
        goToPage(currentPage + 1);
    }
}

function editClip(clipId, videoUrl, title) {
    openVideoEditorModal(clipId, videoUrl, title);
}

function toggleEditedVideos(clipId) {
    const editedList = document.getElementById(`edited-${clipId}`);
    const toggleIcon = document.getElementById(`toggle-${clipId}`);
    
    if (editedList.style.display === 'none') {
        editedList.style.display = 'block';
        toggleIcon.textContent = '▲';
    } else {
        editedList.style.display = 'none';
        toggleIcon.textContent = '▼';
    }
}

/**
 * Delete Functions
 */
async function deleteClip(clipId) {
    showConfirmationModal(
        'Delete Clip', 
        'Are you sure you want to delete this clip and all its subclips?',
        async () => {
            try {
        const response = await safeFetch(`/api/v1/clips/${clipId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showCreationStatus('✅ Clip and all subclips deleted successfully', 'success');
            loadUserClips();
            } else {
                const error = await response.json();
                showCreationStatus(`❌ Failed to delete clip: ${error.detail}`, 'error');
            }
            } catch (error) {
                showCreationStatus(`❌ Network error: ${error.message}`, 'error');
            }
        }
    );
}

async function deleteEditedVideo(editId, clipId) {
    console.log(`Delete button clicked for editId: ${editId}, clipId: ${clipId}`);
    showConfirmationModal(
        'Delete Subclip', 
        'Are you sure you want to delete this subclip?',
        async () => {
            console.log(`Confirmation accepted, proceeding with delete for editId: ${editId}`);
            try {
                const response = await safeFetch(`/api/v1/clips/edited/${editId}`, {
                    method: 'DELETE'
                });

                console.log(`Delete response status: ${response.status}`);
                if (response.ok) {
                    showCreationStatus('✅ Subclip deleted successfully', 'success');
                    loadUserClips();
                } else {
                    const error = await response.json();
                    console.error(`Delete failed:`, error);
                    showCreationStatus(`❌ Failed to delete subclip: ${error.detail}`, 'error');
                }
            } catch (error) {
                console.error(`Delete network error:`, error);
                showCreationStatus(`❌ Network error: ${error.message}`, 'error');
            }
        }
    );
}

/**
 * Bulk Selection Functions
 */
function toggleBulkSelectMode() {
    bulkSelectMode = !bulkSelectMode;
    selectedClipIds.clear();
    updateBulkSelectUI();
}

function updateBulkSelectUI() {
    const bulkSelectBtn = document.getElementById('bulk-select-btn');
    const bulkActions = document.getElementById('bulk-actions');
    const selectionCount = document.getElementById('selection-count');
    const clipItems = document.querySelectorAll('.clip-item');
    
    if (bulkSelectMode) {
        bulkSelectBtn.textContent = '✕ Exit Bulk Select';
        bulkSelectBtn.className = 'btn btn-outline-danger';
        document.body.classList.add('bulk-select-mode');
    } else {
        bulkSelectBtn.textContent = '✓ Bulk Select';
        bulkSelectBtn.className = 'btn btn-outline-primary';
        document.body.classList.remove('bulk-select-mode');
        selectedClipIds.clear();
    }
    
    clipItems.forEach(item => {
        const clipId = item.dataset.clipId;
        if (bulkSelectMode) {
            item.classList.add('selectable');
            if (selectedClipIds.has(clipId)) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        } else {
            item.classList.remove('selectable', 'selected');
        }
    });
    
    selectionCount.textContent = `${selectedClipIds.size} selected`;
    if (bulkSelectMode && selectedClipIds.size > 0) {
        bulkActions.style.display = 'flex';
    } else {
        bulkActions.style.display = 'none';
    }
}

function handleClipClick(event, clipId) {
    if (!bulkSelectMode) {
        return;
    }
    
    event.preventDefault();
    event.stopPropagation();
    
    if (selectedClipIds.has(clipId)) {
        selectedClipIds.delete(clipId);
    } else {
        selectedClipIds.add(clipId);
    }
    
    updateBulkSelectUI();
}

function clearSelection() {
    selectedClipIds.clear();
    updateBulkSelectUI();
}

async function bulkDeleteClips() {
    const selectedIds = Array.from(selectedClipIds);
    
    if (selectedIds.length === 0) {
        showAlert('No clips selected for deletion', 'Warning');
        return;
    }
    
    const clipText = selectedIds.length === 1 ? 'clip' : 'clips';
    showConfirmationModal(
        'Bulk Delete Clips',
        `Are you sure you want to delete ${selectedIds.length} ${clipText} and all their subclips? This action cannot be undone.`,
        async () => {
            try {
                showCreationStatus(`🗑️ Deleting ${selectedIds.length} ${clipText}...`, 'loading');
                
                const response = await safeFetch('/api/v1/clips/bulk-delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ clip_ids: selectedIds })
                });

                if (response.ok) {
                    const result = await response.json();
                    showCreationStatus(`✅ Successfully deleted ${result.deleted_count} ${clipText}`, 'success');
                    selectedClipIds.clear();
                    updateBulkSelectUI();
                    loadUserClips();
                } else {
                    const error = await response.json();
                    showCreationStatus(`❌ Failed to delete ${clipText}: ${error.detail}`, 'error');
                }
            } catch (error) {
                showCreationStatus(`❌ Network error: ${error.message}`, 'error');
            }
        }
    );
}

/**
 * Video Preview Functions
 */
async function previewClip(videoUrl, title, clipId) {
    currentVideoUrl = videoUrl;
    currentClipId = clipId;
    document.getElementById('modal-title').textContent = `Preview: ${title}`;
    
    if (videoPlayer) {
        try {
            videoPlayer.dispose();
        } catch (error) {
        }
        videoPlayer = null;
    }
    
    const videoElement = document.getElementById('video-player');
    if (videoElement) {
        videoElement.className = 'video-js vjs-default-skin';
        videoElement.innerHTML = VIDEO_JS_FALLBACK_HTML;
    }
    
    document.getElementById('video-preview-modal').style.display = 'flex';
    
    // Get secure video URL with token
    const secureVideoUrl = await getSecureMediaUrl(videoUrl, clipId, 'video');
    if (!secureVideoUrl) {
        if (isClipRecentlyCreated(clipId)) {
            showAlert('Video is still processing. Please try again in a few moments.', 'Video Not Ready');
        } else {
            showAlert('Failed to load video. Please try again.', 'Error');
        }
        closeVideoPreview();
        return;
    }
    
    setTimeout(() => {
        async function waitForPreviewElement(maxAttempts = 10, attempt = 0) {
            let videoElement = document.getElementById('video-player');
            
            if (videoElement) {
                initializePreviewPlayer(videoElement, secureVideoUrl);
            } else {
                const modalBody = document.querySelector('#video-preview-modal .modal-body');
                if (modalBody && attempt === 0) {
                    
                    // Find and remove any existing video elements first
                    const existingVideo = modalBody.querySelector('video');
                    if (existingVideo) {
                        existingVideo.remove();
                    }
                    
                    // Create new video element
                    const videoHTML = `
                        <video 
                            id="video-player" 
                            class="video-js vjs-default-skin" 
                            controls 
                            preload="none" 
                            width="100%" 
                            height="400">
                            ${VIDEO_JS_FALLBACK_HTML}
                        </video>
                        <div class="video-controls" style="margin-top: 15px;">
                            <button class="btn btn-primary" onclick="editVideo()">✂️ Edit Video</button>
                            <button class="btn btn-secondary" onclick="closeVideoPreview()">Close</button>
                        </div>
                    `;
                    modalBody.innerHTML = videoHTML;
                    
                    setTimeout(() => waitForPreviewElement(maxAttempts, 1), 50);
                } else if (attempt < maxAttempts) {
                    setTimeout(() => waitForPreviewElement(maxAttempts, attempt + 1), 100);
                } else {
                    console.error('Preview video element not found after multiple attempts');
                    showAlert('Error: Could not find or recreate preview video element', 'Error');
                }
            }
        }
        
        waitForPreviewElement();
    }, 150);
}

function initializePreviewPlayer(videoElement, videoUrl) {
    videoPlayer = initializeVideoJSPlayer(videoElement.id, videoUrl, currentClipId, 'video');
    
    if (videoPlayer) {
        videoPlayer.ready(() => {
            // Preview player is ready
        });
        
        const editButton = document.querySelector('.video-controls .btn-primary');
        if (editButton) {
            editButton.style.display = 'inline-block';
        }
    }
}

function closeVideoPreview() {
    document.getElementById('video-preview-modal').style.display = 'none';
    videoPlayer = cleanupVideoJSPlayer(videoPlayer, 'video-player');
}

async function previewSubclip(videoUrl, title) {
    // Close any open subclip success modal first
    const subclipModal = document.getElementById('subclip-success-modal-editor');
    if (subclipModal) {
        closeSubclipSuccessModalEditor();
        // Add a small delay to ensure the modal is fully closed
        setTimeout(() => openSubclipPreview(videoUrl, title), 100);
        return;
    }
    
    await openSubclipPreview(videoUrl, title);
}

async function openSubclipPreview(videoUrl, title) {
    currentVideoUrl = videoUrl;
    currentClipId = '';
    document.getElementById('modal-title').textContent = `Preview: ${title}`;
    
    if (videoPlayer) {
        try {
            videoPlayer.dispose();
        } catch (error) {
        }
        videoPlayer = null;
    }
    
    const videoElement = document.getElementById('video-player');
    if (videoElement) {
        videoElement.className = 'video-js vjs-default-skin';
        videoElement.innerHTML = VIDEO_JS_FALLBACK_HTML;
    }
    
    document.getElementById('video-preview-modal').style.display = 'flex';
    
    // Extract edit ID from URL and get secure video URL
    let secureVideoUrl = videoUrl;
    const editIdMatch = videoUrl.match(/\/edit\/([^\/\?]+)/);
    if (editIdMatch) {
        const editId = editIdMatch[1];
        secureVideoUrl = await getSecureMediaUrl(videoUrl, editId, 'edit');
        if (!secureVideoUrl) {
            showAlert('Failed to load edited video. Please try again.', 'Error');
            closeVideoPreview();
            return;
        }
    }
    
    setTimeout(() => {
        // Retry logic for video player element
        function tryInitializePlayer(attempt = 1, maxAttempts = 5) {
            try {
                let element = document.getElementById('video-player');
                if (!element) {
                    if (attempt < maxAttempts) {
                        
                        // Recreate the video element completely
                        const modalBody = document.querySelector('#video-preview-modal .modal-body');
                        if (modalBody) {
                            const videoHTML = `
                                <video 
                                    id="video-player" 
                                    class="video-js vjs-default-skin" 
                                    controls 
                                    preload="none" 
                                    width="100%" 
                                    height="400">
                                    ${VIDEO_JS_FALLBACK_HTML}
                                </video>
                                <div class="video-controls" style="margin-top: 15px;">
                                    <button class="btn btn-primary" onclick="editVideo()">✂️ Edit Video</button>
                                    <button class="btn btn-secondary" onclick="closeVideoPreview()">Close</button>
                                </div>
                            `;
                            modalBody.innerHTML = videoHTML;
                        }
                        
                        setTimeout(() => tryInitializePlayer(attempt + 1, maxAttempts), 200);
                        return;
                    } else {
                        throw new Error('Preview video element not found after multiple attempts');
                    }
                }
                
                // Initialize video player using helper function
                videoPlayer = initializeVideoJSPlayer(element.id, secureVideoUrl, null, null);
                
                const editButton = document.querySelector('.video-controls .btn-primary');
                if (editButton) {
                    editButton.style.display = 'none';
                }
                
            } catch (error) {
                console.error('Error initializing video player:', error);
                showAlert('Error loading video player: ' + error.message, 'Error');
            }
        }
        
        // Start the retry logic
        tryInitializePlayer();
    }, 150);
}

/**
 * Modal Functions
 */
function showConfirmationModal(title, message, callback) {
    console.log(`Showing confirmation modal: ${title}`);
    document.getElementById('confirmation-title').textContent = title;
    document.getElementById('confirmation-message').textContent = message;
    confirmationCallback = callback;
    document.getElementById('confirmation-modal').style.display = 'flex';
}

function closeConfirmationModal() {
    document.getElementById('confirmation-modal').style.display = 'none';
    confirmationCallback = null;
}

function showAlert(message, title = 'Alert') {
    document.getElementById('alert-title').textContent = title;
    document.getElementById('alert-message').textContent = message;
    document.getElementById('alert-modal').style.display = 'flex';
}

function closeAlertModal() {
    document.getElementById('alert-modal').style.display = 'none';
}

function toggleSettings() {
    const settingsContent = document.getElementById('settings-content');
    const settingsToggle = document.getElementById('settings-toggle');
    
    if (settingsContent.style.display === 'none' || settingsContent.style.display === '') {
        settingsContent.style.display = 'block';
        settingsToggle.classList.add('rotated');
    } else {
        settingsContent.style.display = 'none';
        settingsToggle.classList.remove('rotated');
    }
}

/**
 * Clip Success Modal Functions
 */
async function showClipSuccessModal(clipData) {
    currentCreatedClipId = clipData.clip_id;
    currentCreatedClipUrl = clipData.download_url;
    currentCreatedClipTitle = clipData.title || 'New Clip';
    
    // Check if clip is longer than 1 minute (60 seconds)
    if (clipData.duration && clipData.duration > 60) {
        // Show notification instead of modal for long clips
        showCreationStatus(`✅ Your clip "${currentCreatedClipTitle}" has been created successfully! It will be available in the View tab in a few moments.`, 'success');
        setTimeout(() => {
            hideCreationStatus();
        }, 5000);
        return;
    }
    
    // Show modal first to ensure video element is in DOM
    document.getElementById('clip-success-modal').style.display = 'flex';
    
    // Small delay to ensure DOM is ready and database transaction is committed
    await new Promise(resolve => setTimeout(resolve, 500));
    
    const videoPlayer = document.getElementById('success-video-player');
    
    // Get secure video URL with token
    
    if (!videoPlayer) {
        console.error('Video player element not found in clip success modal');
        return;
    }
    
    let secureVideoUrl = await getSecureMediaUrl(clipData.download_url, clipData.clip_id, 'video');
    
    // If first attempt fails, wait a bit longer and retry (database might not be committed yet)
    if (!secureVideoUrl) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        secureVideoUrl = await getSecureMediaUrl(clipData.download_url, clipData.clip_id, 'video');
    }
    
    if (secureVideoUrl) {
        videoPlayer.src = secureVideoUrl;
        
        // Add error handling for video loading
        videoPlayer.onerror = function(e) {
            console.error('Video loading error:', e, 'Video error state:', videoPlayer.error);
        };
        
        videoPlayer.onloadstart = function() {
        };
        
        videoPlayer.oncanplay = function() {
        };
        
        videoPlayer.onplay = function() {
        };
        
        // Force load the video
        videoPlayer.load();
    } else {
        console.error('Failed to get secure video URL for clip success modal after retry');
        videoPlayer.src = clipData.download_url; // Fallback to original URL
        videoPlayer.load();
    }
    
    document.getElementById('clip-duration').textContent = 
        clipData.duration ? Math.round(clipData.duration) + 's' : 'Unknown';
    document.getElementById('clip-format-display').textContent = 
        clipData.format ? clipData.format.toUpperCase() : 'MP4';
    document.getElementById('clip-quality-display').textContent = 
        clipData.quality ? clipData.quality.charAt(0).toUpperCase() + clipData.quality.slice(1) : 'Medium';
    
    const downloadBtn = document.getElementById('download-clip-btn');
    // Get separate secure URL for download (with download=true parameter)
    const downloadUrl = await getSecureMediaUrl(clipData.download_url, clipData.clip_id, 'video', true);
    downloadBtn.href = downloadUrl || clipData.download_url;
    downloadBtn.download = clipData.filename || 'clip.mp4';
}

function closeClipSuccessModal() {
    document.getElementById('clip-success-modal').style.display = 'none';
    const videoPlayer = document.getElementById('success-video-player');
    videoPlayer.pause();
    videoPlayer.currentTime = 0;
}

async function downloadClip(clipId, downloadUrl, filename) {
    await downloadMedia(clipId, downloadUrl, filename, 'video');
}

async function downloadSubclip(editId, downloadUrl, filename) {
    await downloadMedia(editId, downloadUrl, filename, 'edit');
}

function editCreatedClip() {
    if (!currentCreatedClipId || !currentCreatedClipUrl) {
        showAlert('No clip data available for editing', 'Error');
        return;
    }
    
    closeClipSuccessModal();
    openVideoEditorModal(currentCreatedClipId, currentCreatedClipUrl, currentCreatedClipTitle);
}

function editVideo() {
    if (!currentVideoUrl) {
        showAlert('No video loaded', 'Error');
        return;
    }
    
    if (!currentClipId) {
        showAlert('No clip ID specified for editing', 'Error');
        return;
    }
    
    const title = document.getElementById('modal-title').textContent.replace('Preview: ', '');
    closeVideoPreview();
    openVideoEditorModal(currentClipId, currentVideoUrl, title);
}

/**
 * Preview Selection Functions
 */
async function previewSelection() {
    if (!currentSessionData || !currentSessionData.has_session) {
        showAlert('⚠️ No active session available for preview. Please select a session first.', 'Warning');
        return;
    }
    
    const timeInputs = getTimeInputValues();
    const { hour: startHour, minute: startMinute, second: startSecond } = timeInputs.start;
    const { hour: endHour, minute: endMinute, second: endSecondValue } = timeInputs.end;
    
    const hasStartTime = startHour !== 0 || startMinute !== 0 || startSecond !== 0;
    const hasEndTime = endHour !== 0 || endMinute !== 0 || endSecondValue !== 0;
    
    if (!hasStartTime && !hasEndTime) {
        showAlert('⚠️ Please set at least a start or end time', 'Warning');
        return;
    }
    
    // Show the modal and start loading
    const modal = document.getElementById('preview-selection-modal');
    const loadingElement = document.getElementById('preview-modal-loading');
    const contentElement = document.getElementById('preview-modal-content');
    const errorElement = document.getElementById('preview-modal-error');
    
    modal.style.display = 'flex';
    loadingElement.style.display = 'block';
    contentElement.style.display = 'none';
    errorElement.style.display = 'none';
    
    let apiUrl = '/api/v1/sessions/preview-frames?';
    const params = [];
    
    if (hasStartTime) {
        const startTime = `${startHour.toString().padStart(2, '0')}:${startMinute.toString().padStart(2, '0')}:${startSecond.toString().padStart(2, '0')}`;
        params.push(`start_time=${encodeURIComponent(startTime)}`);
    }
    
    if (hasEndTime) {
        const endTime = `${endHour.toString().padStart(2, '0')}:${endMinute.toString().padStart(2, '0')}:${endSecondValue.toString().padStart(2, '0')}`;
        params.push(`end_time=${encodeURIComponent(endTime)}`);
    }
    
    // Include session_key if a specific session is selected
    if (currentSessionData && currentSessionData.session && currentSessionData.session.session_key) {
        params.push(`session_key=${encodeURIComponent(currentSessionData.session.session_key)}`);
    }
    
    apiUrl += params.join('&');
    
    try {
        const response = await fetch(apiUrl, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const previewData = await response.json();
        
        if (previewData.status === 'completed') {
            currentPreviewFrames = {};
            
            // Access frames from the frames object, not directly from previewData
            const startFrame = previewData.frames?.start_frame;
            const endFrame = previewData.frames?.end_frame;
            
            if (startFrame) {
                currentPreviewFrames.start_frame_url = startFrame.download_url || startFrame.url;
                currentPreviewFrames.start_frame_id = startFrame.frame_id;
            }
            if (endFrame) {
                currentPreviewFrames.end_frame_url = endFrame.download_url || endFrame.url;
                currentPreviewFrames.end_frame_id = endFrame.frame_id;
            }
            
            const startImg = document.getElementById('preview-modal-start-img');
            const endImg = document.getElementById('preview-modal-end-img');
            const startTimeDisplay = document.getElementById('preview-modal-start-time');
            const endTimeDisplay = document.getElementById('preview-modal-end-time');
            const startFrameDiv = document.getElementById('preview-modal-start-frame');
            const endFrameDiv = document.getElementById('preview-modal-end-frame');
            
            if (startFrame) {
                // Get secure URL for start frame with token
                const startFrameUrl = startFrame.download_url || startFrame.url;
                
                let secureStartUrl = await getSecureMediaUrl(startFrameUrl, startFrame.frame_id, 'snapshot');
                
                // Retry if failed (database might not be committed yet)
                if (!secureStartUrl) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    secureStartUrl = await getSecureMediaUrl(startFrameUrl, startFrame.frame_id, 'snapshot');
                }
                
                startImg.src = secureStartUrl || startFrameUrl;
                startTimeDisplay.textContent = startFrame.timestamp;
                startFrameDiv.style.display = 'block';
            } else {
                startFrameDiv.style.display = 'none';
            }
            
            if (endFrame) {
                // Get secure URL for end frame with token
                const endFrameUrl = endFrame.download_url || endFrame.url;
                
                let secureEndUrl = await getSecureMediaUrl(endFrameUrl, endFrame.frame_id, 'snapshot');
                
                // Retry if failed (database might not be committed yet)
                if (!secureEndUrl) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    secureEndUrl = await getSecureMediaUrl(endFrameUrl, endFrame.frame_id, 'snapshot');
                }
                
                endImg.src = secureEndUrl || endFrameUrl;
                endTimeDisplay.textContent = endFrame.timestamp;
                endFrameDiv.style.display = 'block';
            } else {
                endFrameDiv.style.display = 'none';
            }
            
            loadingElement.style.display = 'none';
            contentElement.style.display = 'flex';
            
        } else {
            throw new Error(previewData.error_message || 'Preview generation failed');
        }
        
    } catch (error) {
        console.error('Preview generation failed:', error);
        
        loadingElement.style.display = 'none';
        errorElement.style.display = 'block';
        
        setTimeout(() => {
            errorElement.style.display = 'none';
        }, 3000);
    }
}

async function closePreviewSelectionModal() {
    document.getElementById('preview-selection-modal').style.display = 'none';
    
    // Clean up preview frames from server
    if (currentPreviewFrames) {
        const frameIds = [];
        if (currentPreviewFrames.start_frame_id) {
            frameIds.push(currentPreviewFrames.start_frame_id);
        }
        if (currentPreviewFrames.end_frame_id) {
            frameIds.push(currentPreviewFrames.end_frame_id);
        }
        
        if (frameIds.length > 0) {
            try {
                const response = await safeFetch('/api/v1/sessions/snapshots/cleanup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ frame_ids: frameIds })
                });
                
                if (!response.ok) {
                    console.warn('Preview frame cleanup failed:', response.status);
                }
            } catch (error) {
                console.error('Error cleaning up preview frames:', error);
            }
        }
        
        currentPreviewFrames = null;
    }
}

/**
 * Large Frame Preview Functions
 */
function openLargeFramePreview(frameType) {
    if (!currentPreviewFrames) {
        console.warn('No preview frames available');
        return;
    }
    
    const modal = document.getElementById('large-frame-preview-modal');
    const img = document.getElementById('large-frame-img');
    const title = document.getElementById('large-frame-title');
    const timestamp = document.getElementById('large-frame-time');
    const frameTypeDisplay = document.getElementById('large-frame-type');
    
    if (frameType === 'start' && currentPreviewFrames.start_frame_url) {
        img.src = currentPreviewFrames.start_frame_url;
        title.textContent = '📍 Start Frame Preview';
        frameTypeDisplay.textContent = 'Start Frame';
        timestamp.textContent = document.getElementById('preview-modal-start-time').textContent;
    } else if (frameType === 'end' && currentPreviewFrames.end_frame_url) {
        img.src = currentPreviewFrames.end_frame_url;
        title.textContent = '🏁 End Frame Preview';
        frameTypeDisplay.textContent = 'End Frame';
        timestamp.textContent = document.getElementById('preview-modal-end-time').textContent;
    } else {
        console.warn(`Frame type '${frameType}' not available or invalid`);
        return;
    }
    
    modal.style.display = 'flex';
    
    // Prevent background scroll
    document.body.style.overflow = 'hidden';
}

function closeLargeFramePreview() {
    const modal = document.getElementById('large-frame-preview-modal');
    modal.style.display = 'none';
    
    // Restore background scroll
    document.body.style.overflow = 'auto';
}

async function cleanupPreviewFrames() {
    if (!currentPreviewFrames) {
        return;
    }
    
    // Clean up preview frames from server
    const frameIds = [];
    if (currentPreviewFrames.start_frame_id) {
        frameIds.push(currentPreviewFrames.start_frame_id);
    }
    if (currentPreviewFrames.end_frame_id) {
        frameIds.push(currentPreviewFrames.end_frame_id);
    }
    
    if (frameIds.length > 0) {
        try {
            const response = await safeFetch('/api/v1/sessions/snapshots/cleanup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ frame_ids: frameIds })
            });
            
            if (!response.ok) {
                console.warn('Preview frame cleanup failed:', response.status);
            }
        } catch (error) {
            console.error('Error cleaning up preview frames:', error);
        }
    }
    
    currentPreviewFrames = null;
    const previewContainer = document.getElementById('clip-preview');
    if (previewContainer) {
        previewContainer.style.display = 'none';
    }
}

/**
 * Tab Switching Functions
 */
function switchTab(tabName) {
    document.querySelectorAll('.tab-button').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    document.getElementById(tabName + '-tab').classList.add('active');
    document.getElementById(tabName + '-tab-content').classList.add('active');
    
    if (tabName === 'create') {
        loadCurrentSession();
    } else if (tabName === 'view') {
        document.getElementById('clips-gallery-section').style.display = 'block';
        loadUserClips();
    }
}

/**
 * Video Editor Modal Functions
 */
class VideoMarkersModal {
    constructor(player) {
        this.player = player;
        this.markers = [];
        this.init();
    }
    
    init() {
        const progressControl = this.player.el().querySelector('.vjs-progress-control');
        if (progressControl) {
            this.markersContainer = videojs.dom.createEl('div', {
                className: 'vjs-markers-container'
            });
            progressControl.appendChild(this.markersContainer);
        }
    }
    
    addMarker(time, text, className = '') {
        if (!this.markersContainer) return null;
        
        const duration = this.player.duration();
        if (!duration) return null;
        
        const percentage = (time / duration) * 100;
        
        const marker = videojs.dom.createEl('div', {
            className: `vjs-marker ${className}`,
            innerHTML: `<div class="vjs-marker-tooltip">${text}</div>`
        });
        
        marker.style.left = percentage + '%';
        
        marker.addEventListener('click', () => {
            this.player.currentTime(time);
        });
        
        this.markersContainer.appendChild(marker);
        
        const markerObj = { time, text, className, element: marker };
        this.markers.push(markerObj);
        
        return markerObj;
    }
    
    removeMarker(marker) {
        if (marker && marker.element) {
            marker.element.remove();
            const index = this.markers.indexOf(marker);
            if (index > -1) {
                this.markers.splice(index, 1);
            }
        }
    }
    
    removeAll() {
        this.markers.forEach(marker => {
            if (marker.element) {
                marker.element.remove();
            }
        });
        this.markers = [];
    }
}

async function openVideoEditorModal(clipId, videoUrl, title) {
    
    currentModalClipId = clipId;
    currentModalVideoUrl = videoUrl;
    currentModalVideoTitle = title || 'Video';
    
    const modal = document.getElementById('video-editor-modal');
    const titleElement = document.getElementById('editor-modal-title');
    
    
    if (!modal) {
        console.error('Video editor modal not found in DOM');
        showAlert('Error: Video editor modal not found', 'Error');
        return;
    }
    
    if (titleElement) {
        titleElement.textContent = `✂️ Editing: ${currentModalVideoTitle}`;
    }
    
    modalStartMarker = null;
    modalEndMarker = null;
    
    modal.style.display = 'flex';
    
    // Get secure video URL with token
    const secureVideoUrl = await getSecureMediaUrl(videoUrl, clipId, 'video');
    if (!secureVideoUrl) {
        if (isClipRecentlyCreated(clipId)) {
            showAlert('Video is still processing. Please try again in a few moments.', 'Video Not Ready');
        } else {
            showAlert('Failed to load video for editing. Please try again.', 'Error');
        }
        closeVideoEditorModal();
        return;
    }
    
    setTimeout(() => {
        loadVideoInModal(secureVideoUrl);
    }, 100);
}

function loadVideoInModal(videoUrl) {
    if (editorModalPlayer) {
        try {
            editorModalPlayer.dispose();
        } catch (error) {
        }
        editorModalPlayer = null;
    }
    
    function waitForElement(maxAttempts = 10, attempt = 0) {
        let videoElement = document.getElementById('editor-modal-video-player');
        
        if (videoElement) {
            initializeVideoPlayer(videoElement, videoUrl);
        } else {
            const videoSection = document.querySelector('#video-editor-modal .editor-video-section');
            if (videoSection && attempt === 0) {
                
                videoSection.innerHTML = `
                    <video 
                        id="editor-modal-video-player" 
                        class="video-js vjs-default-skin" 
                        controls 
                        preload="auto" 
                        width="100%" 
                        height="350">
                        ${VIDEO_JS_FALLBACK_HTML}
                    </video>
                `;
                
                setTimeout(() => waitForElement(maxAttempts, 1), 50);
            } else if (attempt < maxAttempts) {
                setTimeout(() => waitForElement(maxAttempts, attempt + 1), 100);
            } else {
                console.error('Video element not found after multiple attempts and recreation');
                showAlert('Error: Could not find or recreate video element in modal', 'Error');
            }
        }
    }
    
    waitForElement();
}

function initializeVideoPlayer(videoElement, videoUrl) {
    editorModalPlayer = initializeVideoJSPlayer(videoElement.id, videoUrl, currentModalClipId, 'video');
    
    if (editorModalPlayer) {
        editorModalPlayer.ready(() => {
            editorModalPlayer.markers = new VideoMarkersModal(editorModalPlayer);
        });
    }
}

function closeVideoEditorModal() {
    document.getElementById('video-editor-modal').style.display = 'none';
    
    editorModalPlayer = cleanupVideoJSPlayer(editorModalPlayer, 'editor-modal-video-player');
    
    modalStartMarker = null;
    modalEndMarker = null;
    
    document.getElementById('progress-container-modal').style.display = 'none';
    document.getElementById('process-btn-modal').disabled = false;
    document.getElementById('process-btn-modal').textContent = '🎬 Process Video';
    document.getElementById('start-time-modal').textContent = 'Not set';
    document.getElementById('end-time-modal').textContent = 'Not set';
    document.getElementById('trim-duration-modal').textContent = '--';
}

function setStartMarkerModal() {
    if (!editorModalPlayer || !editorModalPlayer.markers) return;
    
    const currentTime = editorModalPlayer.currentTime();
    
    if (modalStartMarker !== null) {
        editorModalPlayer.markers.removeMarker(modalStartMarker);
    }
    
    modalStartMarker = editorModalPlayer.markers.addMarker(currentTime, 'Start', 'start-marker');
    updateMarkerInfoModal();
}

function setEndMarkerModal() {
    if (!editorModalPlayer || !editorModalPlayer.markers) return;
    
    const currentTime = editorModalPlayer.currentTime();
    
    if (modalEndMarker !== null) {
        editorModalPlayer.markers.removeMarker(modalEndMarker);
    }
    
    modalEndMarker = editorModalPlayer.markers.addMarker(currentTime, 'End', 'end-marker');
    updateMarkerInfoModal();
}

function clearMarkersModal() {
    if (!editorModalPlayer || !editorModalPlayer.markers) return;
    
    editorModalPlayer.markers.removeAll();
    modalStartMarker = null;
    modalEndMarker = null;
    updateMarkerInfoModal();
}

function updateMarkerInfoModal() {
    const startTime = modalStartMarker ? formatTimeModal(modalStartMarker.time) : 'Not set';
    const endTime = modalEndMarker ? formatTimeModal(modalEndMarker.time) : 'Not set';
    
    document.getElementById('start-time-modal').textContent = startTime;
    document.getElementById('end-time-modal').textContent = endTime;
    
    if (modalStartMarker && modalEndMarker) {
        const duration = modalEndMarker.time - modalStartMarker.time;
        document.getElementById('trim-duration-modal').textContent = formatTimeModal(duration);
    } else {
        document.getElementById('trim-duration-modal').textContent = '--';
    }
}

function formatTimeModal(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hrs > 0) {
        return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
}

function previewTrimModal() {
    if (!modalStartMarker || !modalEndMarker) {
        showAlert('Please set both start and end markers', 'Warning');
        return;
    }
    
    if (modalStartMarker.time >= modalEndMarker.time) {
        showAlert('Start time must be before end time', 'Warning');
        return;
    }
    
    editorModalPlayer.currentTime(modalStartMarker.time);
    editorModalPlayer.play();
    
    const checkTime = setInterval(() => {
        if (editorModalPlayer.currentTime() >= modalEndMarker.time) {
            editorModalPlayer.pause();
            clearInterval(checkTime);
        }
    }, 100);
}

async function processVideoModal() {
    if (!modalStartMarker || !modalEndMarker) {
        showAlert('Please set both start and end markers', 'Warning');
        return;
    }
    
    if (modalStartMarker.time >= modalEndMarker.time) {
        showAlert('Start time must be before end time', 'Warning');
        return;
    }
    
    if (!currentModalClipId) {
        showAlert('No clip ID specified for editing', 'Error');
        return;
    }
    
    showProcessingModal();
    
    try {
        const response = await safeFetch('/api/v1/clips/edit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                source_clip_id: currentModalClipId,
                start_time: formatTimeModal(modalStartMarker.time),
                end_time: formatTimeModal(modalEndMarker.time),
                quality: 'medium',
                format: 'mp4',
                include_metadata: true
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.status === 'completed') {
                await finishProcessingModal(result);
            } else {
                throw new Error(result.error_message || 'Processing failed');
            }
        } else if (response.status === 403) {
            const error = await response.json();
            if (error.detail && error.detail.includes('Video limit exceeded')) {
                throw new Error(error.detail);
            } else {
                throw new Error(error.detail || 'Processing failed');
            }
        } else {
            const result = await response.json();
            throw new Error(result.error_message || result.detail || 'Processing failed');
        }
        
    } catch (error) {
        console.error('Error processing video:', error);
        document.getElementById('progress-text-modal').textContent = 
            `❌ Error: ${error.message}`;
        document.getElementById('process-btn-modal').disabled = false;
        document.getElementById('process-btn-modal').textContent = '🎬 Process Video';
    }
}

function showProcessingModal() {
    document.getElementById('progress-container-modal').style.display = 'block';
    document.getElementById('process-btn-modal').disabled = true;
    document.getElementById('process-btn-modal').textContent = '⏳ Processing...';
}

async function finishProcessingModal(result) {
    document.getElementById('progress-fill-modal').style.width = '100%';
    document.getElementById('progress-text-modal').textContent = '✅ Processing complete!';
    document.getElementById('process-btn-modal').disabled = false;
    document.getElementById('process-btn-modal').textContent = '🎬 Process Video';
    
    document.getElementById('progress-container-modal').style.display = 'none';
    closeVideoEditorModal();
    
    // Mark this subclip as recently created for better error handling
    if (result.edit_id) {
        markClipAsRecentlyCreated(result.edit_id);
    }
    
    await showSubclipSuccessModalFromEditor(result);
    
    // Delay refresh to avoid interfering with video player initialization
    setTimeout(() => {
        loadUserClips();
    }, 1000);
}

async function showSubclipSuccessModalFromEditor(result) {
    // Check if subclip is longer than 1 minute (60 seconds)
    if (result.duration && result.duration > 60) {
        // Show notification instead of modal for long subclips
        showAlert(`✅ Your subclip has been created successfully! It will be available in the View tab in a few moments.`, 'Subclip Created');
        return;
    }
    
    const subclipModal = document.createElement('div');
    subclipModal.id = 'subclip-success-modal-editor';
    subclipModal.className = 'modal';
    subclipModal.style.display = 'flex';
    subclipModal.innerHTML = `
        <div class="modal-content clip-success-modal">
            <div class="modal-header">
                <button class="modal-close" onclick="closeSubclipSuccessModalEditor()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="clip-success-content">
                    <div class="clip-preview-section">
                        <video 
                            id="subclip-video-player-editor" 
                            class="success-video-preview" 
                            controls 
                            preload="metadata"
                            width="100%"
                            height="500">
                            <p>Your browser doesn't support HTML5 video.</p>
                        </video>
                    </div>
                    
                    <div class="clip-details">
                        <div class="detail-item">
                            <span class="detail-label">Duration:</span>
                            <span class="detail-value">${result.duration ? Math.round(result.duration) + 's' : '-'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Format:</span>
                            <span class="detail-value">MP4</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Quality:</span>
                            <span class="detail-value">Medium</span>
                        </div>
                    </div>
                </div>
                
                <div class="modal-actions">
                    <a id="subclip-download-btn-editor" href="${result.download_url}" download="${result.filename || 'subclip.mp4'}" class="btn btn-primary">📥 Download Subclip</a>
                    <button class="btn btn-secondary" onclick="createAnotherSubclipEditor()">✂️ Create Another</button>
                    <button class="btn btn-secondary" onclick="closeSubclipSuccessModalEditor()">Close</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(subclipModal);
    
    // Set secure video URL with token after modal is added to DOM
    const videoElement = document.getElementById('subclip-video-player-editor');
    if (videoElement && result.download_url) {
        // Extract edit_id from download_url (format: /api/v1/storage/edit/{edit_id})
        const editIdMatch = result.download_url.match(/\/edit\/([^\/\?]+)/);
        if (editIdMatch) {
            const editId = editIdMatch[1];
            
            try {
                const secureVideoUrl = await getSecureMediaUrl(result.download_url, editId, 'edit');
                if (secureVideoUrl) {
                    videoElement.src = secureVideoUrl;
                    
                    // Also update the download button href with download=true parameter
                    const downloadBtn = document.getElementById('subclip-download-btn-editor');
                    if (downloadBtn) {
                        const downloadUrl = await getSecureMediaUrl(result.download_url, editId, 'edit', true);
                        downloadBtn.href = downloadUrl || result.download_url;
                    }
                } else {
                    console.error('Failed to get secure video URL for subclip success modal');
                    videoElement.src = result.download_url; // Fallback to original URL
                }
            } catch (error) {
                console.error('Error getting secure video URL for subclip success modal:', error);
                videoElement.src = result.download_url; // Fallback to original URL
            }
        } else {
            videoElement.src = result.download_url; // Fallback to original URL
        }
    }
    
    subclipModal.onclick = function(e) {
        if (e.target === this) {
            closeSubclipSuccessModalEditor();
        }
    };
}

function closeSubclipSuccessModalEditor() {
    const modal = document.getElementById('subclip-success-modal-editor');
    if (modal) {
        const video = document.getElementById('subclip-video-player-editor');
        if (video) {
            video.pause();
            video.currentTime = 0;
        }
        modal.remove();
    }
}

function createAnotherSubclipEditor() {
    closeSubclipSuccessModalEditor();
    openVideoEditorModal(currentModalClipId, currentModalVideoUrl, currentModalVideoTitle);
}

/**
 * Quality Management Functions
 */
function updateQualityDescription() {
    const qualitySelect = document.getElementById('clip-quality');
    const qualityInfo = document.getElementById('quality-info');
    const qualityDescriptions = {
        'low': 'Fast encoding, smaller file size, lower visual quality',
        'medium': 'Balanced quality and file size',
        'high': 'Best quality, larger file size, slower encoding'
    };
    
    const selectedQuality = qualitySelect.value;
    qualityInfo.innerHTML = `<span class="quality-description">${qualityDescriptions[selectedQuality]}</span>`;
}

/**
 * Clip Rename Functions
 */
function startRenaming(clipId, originalTitle) {
    const titleElement = document.getElementById(`clip-title-${clipId}`);
    const inputElement = document.getElementById(`clip-title-input-${clipId}`);
    
    if (!titleElement || !inputElement) return;
    
    titleElement.style.display = 'none';
    inputElement.style.display = 'block';
    inputElement.focus();
    inputElement.select();
}

function cancelRenaming(clipId, originalTitle) {
    const titleElement = document.getElementById(`clip-title-${clipId}`);
    const inputElement = document.getElementById(`clip-title-input-${clipId}`);
    
    if (!titleElement || !inputElement) return;
    
    inputElement.value = originalTitle.replace(/\\'/g, "'").replace(/\\"/g, '"');
    titleElement.style.display = 'block';
    inputElement.style.display = 'none';
}

function handleRenameKeydown(event, clipId, originalTitle) {
    if (event.key === 'Enter') {
        event.preventDefault();
        saveRename(clipId, originalTitle);
    } else if (event.key === 'Escape') {
        event.preventDefault();
        cancelRenaming(clipId, originalTitle);
    }
}

async function saveRename(clipId, originalTitle) {
    const titleElement = document.getElementById(`clip-title-${clipId}`);
    const inputElement = document.getElementById(`clip-title-input-${clipId}`);
    
    if (!titleElement || !inputElement) return;
    
    const newTitle = inputElement.value.trim();
    
    if (!newTitle) {
        showAlert('Clip name cannot be empty', 'Warning');
        cancelRenaming(clipId, originalTitle);
        return;
    }
    
    if (newTitle === originalTitle.replace(/\\'/g, "'").replace(/\\"/g, '"')) {
        cancelRenaming(clipId, originalTitle);
        return;
    }
    
    try {
        const response = await safeFetch(`/api/v1/clips/${clipId}/metadata`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ title: newTitle })
        });
        
        if (response.ok) {
            titleElement.textContent = newTitle;
            titleElement.style.display = 'block';
            inputElement.style.display = 'none';
            showCreationStatus('✅ Clip renamed successfully', 'success');
        } else {
            const error = await response.json();
            showAlert(`Failed to rename clip: ${error.detail}`, 'Error');
            cancelRenaming(clipId, originalTitle);
        }
    } catch (error) {
        showAlert(`Network error: ${error.message}`, 'Error');
        cancelRenaming(clipId, originalTitle);
    }
}

/**
 * Application Initialization
 */
document.addEventListener('DOMContentLoaded', async function() {
    // Set up event listeners
    document.getElementById('logout-btn').addEventListener('click', logout);
    document.getElementById('refresh-session-btn').addEventListener('click', loadCurrentSession);
    document.getElementById('use-current-time-btn').addEventListener('click', useCurrentTimeAsStart);
    document.getElementById('use-current-time-end-btn').addEventListener('click', useCurrentTimeAsEnd);
    document.getElementById('clip-quality').addEventListener('change', updateQualityDescription);
    
    // Make app logo refresh the whole app
    document.querySelector('.app-header h1').addEventListener('click', refreshApp);
    
    // Set up pagination event listeners
    document.getElementById('clips-per-page').addEventListener('change', changePageSize);
    document.getElementById('prev-page-btn').addEventListener('click', goToPreviousPage);
    document.getElementById('next-page-btn').addEventListener('click', goToNextPage);
    
    // Set up modal click handlers
    setupModalCloseHandler('video-editor-modal', closeVideoEditorModal);
    setupModalCloseHandler('frame-selection-modal', closeFrameSelectionModal);
    setupModalCloseHandler('preview-selection-modal', closePreviewSelectionModal);
    setupModalCloseHandler('large-frame-preview-modal', closeLargeFramePreview);
    setupModalCloseHandler('confirmation-modal', closeConfirmationModal);
    setupModalCloseHandler('alert-modal', closeAlertModal);
    setupModalCloseHandler('clip-success-modal', closeClipSuccessModal);
    
    // Confirmation modal event handlers
    document.getElementById('confirm-yes').onclick = function() {
        console.log('Confirm yes clicked, callback exists:', !!confirmationCallback);
        if (confirmationCallback) {
            confirmationCallback();
        }
        closeConfirmationModal();
    };
    
    // Initialize CSRF token (now synchronous)
    ensureCSRFToken();
    
    // Initialize application
    currentUser = await getCurrentUser();
    
    if (currentUser) {
        displayUserInfo(currentUser);
        showDashboard();
        await loadCurrentSession();
    } else {
        showError();
    }
});