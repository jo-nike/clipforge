class PlexPlayerMonitor {
  constructor() {
    this.player = null;
    this.currentTime = 0;
    this.duration = 0;
    this.sessionKey = null;
    this.mediaInfo = null;
    this.observers = [];
    this.timeUpdateHandler = null;
  }

  async detectPlayer() {
    return new Promise((resolve) => {
      const checkForPlayer = () => {
        const video = document.querySelector('video');
        if (video) {
          this.player = video;
          this.attachPlayerListeners();
          resolve(true);
          return true;
        }
        return false;
      };

      if (checkForPlayer()) {
        return;
      }

      const observer = new MutationObserver(() => {
        if (checkForPlayer()) {
          observer.disconnect();
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true
      });

      this.observers.push(observer);

      setTimeout(() => {
        observer.disconnect();
        resolve(false);
      }, 30000);
    });
  }

  attachPlayerListeners() {
    if (!this.player) return;

    this.timeUpdateHandler = () => {
      this.currentTime = this.player.currentTime;
      this.duration = this.player.duration;
    };

    this.player.addEventListener('timeupdate', this.timeUpdateHandler);
    this.player.addEventListener('loadedmetadata', () => {
      this.duration = this.player.duration;
    });
  }

  extractSessionInfo() {
    this.sessionKey = null;
    this.mediaInfo = {};

    const urlParams = new URLSearchParams(window.location.search);
    const keyFromUrl = urlParams.get('key');
    
    if (keyFromUrl) {
      this.sessionKey = keyFromUrl;
    }

    if (this.player) {
      const sessionFromPlayer = this.player.getAttribute('data-session-key');
      if (sessionFromPlayer) {
        this.sessionKey = sessionFromPlayer;
      }
    }

    const reactContainer = document.querySelector('[data-reactroot]');
    if (reactContainer) {
      try {
        const reactKey = Object.keys(reactContainer).find(key => 
          key.startsWith('__reactInternalInstance') || 
          key.startsWith('__reactFiber')
        );
        
        if (reactKey && reactContainer[reactKey]) {
          const fiber = reactContainer[reactKey];
          this.extractReactProps(fiber);
        }
      } catch (error) {
        console.log('Could not extract React props:', error);
      }
    }

    const pathMatch = window.location.pathname.match(/\/server\/([^\/]+)\/details/);
    if (pathMatch) {
      this.mediaInfo.serverId = pathMatch[1];
    }

    const metadataMatch = window.location.pathname.match(/metadata\/(\d+)/);
    if (metadataMatch) {
      this.mediaInfo.metadataId = metadataMatch[1];
    }

    this.extractMediaTitle();

    return {
      sessionKey: this.sessionKey,
      mediaInfo: this.mediaInfo
    };
  }

  extractReactProps(fiber) {
    let current = fiber;
    while (current) {
      if (current.memoizedProps) {
        const props = current.memoizedProps;
        
        if (props.playSession?.key) {
          this.sessionKey = props.playSession.key;
        }
        
        if (props.metadata) {
          this.mediaInfo = {
            ...this.mediaInfo,
            title: props.metadata.title,
            type: props.metadata.type,
            key: props.metadata.key,
            ratingKey: props.metadata.ratingKey
          };
        }
        
        if (props.session?.key) {
          this.sessionKey = props.session.key;
        }
      }
      
      current = current.return;
    }
  }

  extractMediaTitle() {
    const titleElement = document.querySelector('[data-testid="metadata-title"], .MetadataPosterTitle-title, h1');
    if (titleElement) {
      this.mediaInfo.title = titleElement.textContent.trim();
    }

    const showTitleElement = document.querySelector('[data-testid="metadata-show-title"], .MetadataPosterTitle-showTitle');
    if (showTitleElement) {
      this.mediaInfo.showTitle = showTitleElement.textContent.trim();
    }

    const seasonEpisode = document.querySelector('[data-testid="metadata-season-episode"]');
    if (seasonEpisode) {
      const match = seasonEpisode.textContent.match(/S(\d+) · E(\d+)/);
      if (match) {
        this.mediaInfo.season = parseInt(match[1]);
        this.mediaInfo.episode = parseInt(match[2]);
      }
    }
  }

  getCurrentPlaybackInfo() {
    return {
      currentTime: this.currentTime,
      duration: this.duration,
      sessionKey: this.sessionKey,
      mediaInfo: this.mediaInfo,
      isPlaying: this.player && !this.player.paused
    };
  }

  generateClipTitle(direction = 'next') {
    const timestamp = this.formatTimestamp(this.currentTime);
    let baseTitle = 'Clip';

    if (this.mediaInfo.showTitle && this.mediaInfo.title) {
      baseTitle = `${this.mediaInfo.showTitle} - ${this.mediaInfo.title}`;
    } else if (this.mediaInfo.title) {
      baseTitle = this.mediaInfo.title;
    }

    if (this.mediaInfo.season && this.mediaInfo.episode) {
      baseTitle += ` S${String(this.mediaInfo.season).padStart(2, '0')}E${String(this.mediaInfo.episode).padStart(2, '0')}`;
    }

    const directionText = direction === 'previous' ? 'before' : 'after';
    return `${baseTitle} - Clip ${directionText} ${timestamp}`;
  }

  formatTimestamp(seconds) {
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

  destroy() {
    if (this.player && this.timeUpdateHandler) {
      this.player.removeEventListener('timeupdate', this.timeUpdateHandler);
    }

    this.observers.forEach(observer => observer.disconnect());
    this.observers = [];
  }
}

export default PlexPlayerMonitor;