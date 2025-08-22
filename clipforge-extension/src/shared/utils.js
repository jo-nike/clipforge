export function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '0s';
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  const parts = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
  
  return parts.join(' ');
}

export function formatTimestamp(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h${minutes}m${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m${secs}s`;
  } else {
    return `${secs}s`;
  }
}

export function formatDate(dateString) {
  if (!dateString) return '';
  
  const date = new Date(dateString);
  const now = new Date();
  const diff = now - date;
  
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  
  if (seconds < 60) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  
  return date.toLocaleDateString();
}

export function generateClipTitle(mediaInfo, timestamp, direction = 'next') {
  let baseTitle = 'Clip';

  if (mediaInfo.showTitle && mediaInfo.title) {
    baseTitle = `${mediaInfo.showTitle} - ${mediaInfo.title}`;
  } else if (mediaInfo.title) {
    baseTitle = mediaInfo.title;
  }

  if (mediaInfo.season && mediaInfo.episode) {
    baseTitle += ` S${String(mediaInfo.season).padStart(2, '0')}E${String(mediaInfo.episode).padStart(2, '0')}`;
  }

  const directionText = direction === 'previous' ? 'before' : 'after';
  return `${baseTitle} - Clip ${directionText} ${timestamp}`;
}

export function parseShortcut(shortcut) {
  const parts = shortcut.split('+');
  return {
    altKey: parts.includes('Alt'),
    ctrlKey: parts.includes('Ctrl'),
    shiftKey: parts.includes('Shift'),
    metaKey: parts.includes('Meta') || parts.includes('Cmd'),
    key: parts[parts.length - 1].replace(/[\[\]]/g, '')
  };
}

export function matchesShortcut(event, shortcut) {
  const parsed = typeof shortcut === 'string' ? parseShortcut(shortcut) : shortcut;
  
  return event.altKey === parsed.altKey &&
         event.ctrlKey === parsed.ctrlKey &&
         event.shiftKey === parsed.shiftKey &&
         event.metaKey === parsed.metaKey &&
         event.key === parsed.key;
}

export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

export function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

export async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function extractDomain(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname;
  } catch {
    return null;
  }
}

export function isPlexDomain(url) {
  const domain = extractDomain(url || window.location.href);
  return domain && (domain.includes('plex.tv'));
}

export function validateUrl(url) {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

export function sanitizeFilename(filename) {
  return filename.replace(/[^a-z0-9_\-]/gi, '_').substring(0, 255);
}

export default {
  formatTime,
  formatDuration,
  formatTimestamp,
  formatDate,
  generateClipTitle,
  parseShortcut,
  matchesShortcut,
  debounce,
  throttle,
  sleep,
  extractDomain,
  isPlexDomain,
  validateUrl,
  sanitizeFilename
};