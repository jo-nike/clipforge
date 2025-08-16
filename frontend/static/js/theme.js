/**
 * Theme Management System
 * Handles dark/light theme switching with localStorage persistence
 */

class ThemeManager {
    constructor() {
        this.themes = {
            light: 'light',
            dark: 'dark'
        };
        
        this.currentTheme = null;
        this.toggleButton = null;
        this.prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
        
        this.init();
    }
    
    /**
     * Initialize theme manager
     */
    init() {
        // Set initial theme
        this.setInitialTheme();
        
        // Create theme toggle button
        this.createToggleButton();
        
        // Listen for system theme changes
        this.prefersDarkScheme.addEventListener('change', () => {
            if (!this.hasStoredPreference()) {
                this.setTheme(this.getSystemTheme());
            }
        });
        
        // Add smooth transition class to body
        document.body.classList.add('theme-transition');
        
        // Dispatch theme loaded event
        this.dispatchThemeEvent('themeLoaded', this.currentTheme);
    }
    
    /**
     * Set initial theme based on stored preference or system preference
     */
    setInitialTheme() {
        const storedTheme = this.getStoredTheme();
        const systemTheme = this.getSystemTheme();
        
        // Priority: stored preference > system preference > default (dark)
        const initialTheme = storedTheme || systemTheme || this.themes.dark;
        this.setTheme(initialTheme);
    }
    
    /**
     * Get stored theme from localStorage
     */
    getStoredTheme() {
        try {
            return localStorage.getItem('clippex-theme');
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Check if user has a stored theme preference
     */
    hasStoredPreference() {
        return this.getStoredTheme() !== null;
    }
    
    /**
     * Get system theme preference
     */
    getSystemTheme() {
        return this.prefersDarkScheme.matches ? this.themes.dark : this.themes.light;
    }
    
    /**
     * Store theme preference in localStorage
     */
    storeTheme(theme) {
        try {
            localStorage.setItem('clippex-theme', theme);
        } catch (e) {
        }
    }
    
    /**
     * Set theme and update UI
     */
    setTheme(theme) {
        if (!Object.values(this.themes).includes(theme)) {
            theme = this.themes.dark;
        }
        
        this.currentTheme = theme;
        
        // Update document attribute
        document.documentElement.setAttribute('data-theme', theme);
        
        // Update toggle button
        this.updateToggleButton();
        
        // Store preference
        this.storeTheme(theme);
        
        // Dispatch theme change event
        this.dispatchThemeEvent('themeChanged', theme);
        
        // Update meta theme-color for mobile browsers
        this.updateMetaThemeColor(theme);
    }
    
    /**
     * Toggle between light and dark themes
     */
    toggleTheme() {
        const newTheme = this.currentTheme === this.themes.dark 
            ? this.themes.light 
            : this.themes.dark;
        
        this.setTheme(newTheme);
        
        // Add animation class for visual feedback
        this.animateToggle();
    }
    
    /**
     * Create floating theme toggle button
     */
    createToggleButton() {
        // Check if we're on a page that should have the toggle in header
        const isAppPage = document.querySelector('.app-header');
        
        if (isAppPage) {
            this.createHeaderToggle();
        } else {
            this.createFloatingToggle();
        }
    }
    
    /**
     * Create floating toggle button for login page
     */
    createFloatingToggle() {
        this.toggleButton = document.createElement('button');
        this.toggleButton.className = 'theme-toggle';
        this.toggleButton.setAttribute('aria-label', 'Toggle theme');
        this.toggleButton.setAttribute('title', 'Toggle dark/light theme');
        
        this.updateToggleButton();
        
        this.toggleButton.addEventListener('click', () => {
            this.toggleTheme();
        });
        
        document.body.appendChild(this.toggleButton);
    }
    
    /**
     * Create header toggle button for app pages
     */
    createHeaderToggle() {
        const headerContent = document.querySelector('.header-content');
        const userInfo = document.querySelector('.user-info');
        
        if (headerContent && userInfo) {
            this.toggleButton = document.createElement('button');
            this.toggleButton.className = 'theme-toggle header-theme-toggle';
            this.toggleButton.setAttribute('aria-label', 'Toggle theme');
            this.toggleButton.setAttribute('title', 'Toggle dark/light theme');
            
            this.updateToggleButton();
            
            this.toggleButton.addEventListener('click', () => {
                this.toggleTheme();
            });
            
            userInfo.appendChild(this.toggleButton);
        }
    }
    
    /**
     * Update toggle button icon and aria-label
     */
    updateToggleButton() {
        if (!this.toggleButton) return;
        
        const isDark = this.currentTheme === this.themes.dark;
        const icon = isDark ? '☀️' : '🌙';
        const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';
        
        this.toggleButton.innerHTML = icon;
        this.toggleButton.setAttribute('aria-label', label);
        this.toggleButton.setAttribute('title', label);
    }
    
    /**
     * Add animation effect to toggle button
     */
    animateToggle() {
        if (!this.toggleButton) return;
        
        this.toggleButton.style.transform = 'scale(0.8) rotate(180deg)';
        
        setTimeout(() => {
            this.toggleButton.style.transform = '';
        }, 200);
    }
    
    /**
     * Update meta theme-color for mobile browsers
     */
    updateMetaThemeColor(theme) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        
        // Set appropriate color based on theme
        const colors = {
            light: '#F8FAFC',
            dark: '#0F172A'
        };
        
        metaThemeColor.content = colors[theme] || colors.dark;
    }
    
    /**
     * Dispatch custom theme events
     */
    dispatchThemeEvent(eventName, theme) {
        const event = new CustomEvent(eventName, {
            detail: {
                theme: theme,
                isDark: theme === this.themes.dark,
                isLight: theme === this.themes.light
            }
        });
        
        document.dispatchEvent(event);
    }
    
    /**
     * Get current theme
     */
    getCurrentTheme() {
        return this.currentTheme;
    }
    
    /**
     * Check if current theme is dark
     */
    isDarkTheme() {
        return this.currentTheme === this.themes.dark;
    }
    
    /**
     * Check if current theme is light
     */
    isLightTheme() {
        return this.currentTheme === this.themes.light;
    }
    
    /**
     * Force set theme (useful for testing or admin controls)
     */
    forceTheme(theme) {
        this.setTheme(theme);
    }
    
    /**
     * Reset to system preference
     */
    resetToSystem() {
        try {
            localStorage.removeItem('clippex-theme');
        } catch (e) {
        }
        
        this.setTheme(this.getSystemTheme());
    }
    
    /**
     * Add theme-aware classes to elements
     */
    addThemeClasses(element, lightClass, darkClass) {
        if (!element) return;
        
        const removeClass = this.isDarkTheme() ? lightClass : darkClass;
        const addClass = this.isDarkTheme() ? darkClass : lightClass;
        
        element.classList.remove(removeClass);
        element.classList.add(addClass);
    }
    
    /**
     * Cleanup method
     */
    destroy() {
        if (this.toggleButton && this.toggleButton.parentNode) {
            this.toggleButton.parentNode.removeChild(this.toggleButton);
        }
        
        this.prefersDarkScheme.removeEventListener('change', this.handleSystemThemeChange);
        document.body.classList.remove('theme-transition');
    }
}

// Utility functions for theme-aware styling
const ThemeUtils = {
    /**
     * Get CSS variable value for current theme
     */
    getCSSVariable(variableName) {
        return getComputedStyle(document.documentElement)
            .getPropertyValue(`--${variableName}`)
            .trim();
    },
    
    /**
     * Set CSS variable dynamically
     */
    setCSSVariable(variableName, value) {
        document.documentElement.style.setProperty(`--${variableName}`, value);
    },
    
    /**
     * Apply theme-aware styles to canvas elements
     */
    styleCanvas(canvas, isDark = null) {
        if (!canvas) return;
        
        const theme = isDark !== null ? isDark : window.themeManager?.isDarkTheme();
        const ctx = canvas.getContext('2d');
        
        if (ctx) {
            // Set appropriate colors for canvas rendering
            ctx.fillStyle = theme ? '#1E293B' : '#FFFFFF';
            ctx.strokeStyle = theme ? '#F1F5F9' : '#1E293B';
        }
    },
    
    /**
     * Get theme-appropriate color
     */
    getThemeColor(lightColor, darkColor) {
        return window.themeManager?.isDarkTheme() ? darkColor : lightColor;
    }
};

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ThemeManager, ThemeUtils };
}

// Event listeners for theme changes (for other scripts to hook into)
document.addEventListener('themeChanged', (event) => {
    const { theme, isDark } = event.detail;
    
    // Update any theme-dependent elements
    const timeline = document.getElementById('timeline-canvas');
    if (timeline) {
        ThemeUtils.styleCanvas(timeline, isDark);
    }
    
    // Update any charts or visualizations
    const charts = document.querySelectorAll('.chart-canvas');
    charts.forEach(chart => {
        ThemeUtils.styleCanvas(chart, isDark);
    });
    
});

// Keyboard shortcut for theme toggle (Ctrl/Cmd + Shift + T)
document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'T') {
        event.preventDefault();
        if (window.themeManager) {
            window.themeManager.toggleTheme();
        }
    }
});

// Export to global scope
window.ThemeUtils = ThemeUtils;