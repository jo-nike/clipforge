# ClipForge Browser Extension

Browser extension for creating instant clips from Plex with one click. Integrates seamlessly with the ClipForge API to provide quick clip creation directly from the Plex web player.

## Features

- **Quick Clip Buttons**: Two buttons injected into Plex player controls
  - `[-30s]`: Create a clip from the last 30 seconds
  - `[+30s]`: Create a clip for the next 30 seconds
- **Keyboard Shortcuts**: Default shortcuts (customizable)
  - `Alt + [`: Previous clip
  - `Alt + ]`: Next clip
- **Auto-generated Titles**: Smart title generation based on media metadata
- **Recent Clips View**: See your recent clips in the extension popup
- **Customizable Settings**: Adjust clip duration, shortcuts, and API endpoint

## Installation

### Development Mode

#### Chrome
1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" in the top right
3. Click "Load unpacked"
4. Select the `clipforge-extension` directory
5. The extension icon will appear in your toolbar

#### Firefox
1. Open Firefox and navigate to `about:debugging`
2. Click "This Firefox"
3. Click "Load Temporary Add-on"
4. Select the `manifest.v2.json` file in the `clipforge-extension` directory
5. The extension will be loaded temporarily

### Production Build

```bash
# Install dependencies
npm install

# Build for Chrome
npm run build:chrome

# Build for Firefox
npm run build:firefox

# Build for both
npm run build:all
```

The built extensions will be in:
- `build/clipforge-chrome.zip` - Ready for Chrome Web Store
- `build/clipforge-firefox.zip` - Ready for Firefox Add-ons

## Usage

1. **Connect to ClipForge**:
   - Click the extension icon
   - Click "Connect to ClipForge"
   - Authenticate with your Plex account

2. **Create Clips**:
   - Navigate to any video in Plex web player
   - Use the injected buttons or keyboard shortcuts
   - Clips are automatically created and sent to ClipForge

3. **Configure Settings**:
   - Click the settings button in the popup
   - Adjust clip duration (15s to 5 minutes)
   - Customize keyboard shortcuts
   - Set your ClipForge API URL

## Configuration

Default settings can be modified in the options page:

- **API URL**: `http://localhost:8000` (change if your ClipForge instance is elsewhere)
- **Clip Duration**: 30 seconds (adjustable from 15 seconds to 5 minutes)
- **Auto-generate Titles**: Enabled by default
- **Keyboard Shortcuts**: Customizable through the settings page

## Development

### Project Structure

```
clipforge-extension/
├── manifest.json           # Chrome manifest (v3)
├── manifest.v2.json        # Firefox manifest (v2)
├── src/
│   ├── background/        # Service worker/background scripts
│   ├── content/           # Content scripts for Plex integration
│   ├── popup/             # Extension popup UI
│   ├── options/           # Settings page
│   └── shared/            # Shared utilities and constants
├── icons/                 # Extension icons
└── build/                 # Build output
```

### Key Components

- **Player Monitor**: Tracks video playback and extracts session information
- **Button Injector**: Injects ClipForge buttons into Plex player controls
- **API Client**: Handles communication with ClipForge backend
- **Auth Manager**: Manages Plex OAuth and token refresh

### Testing

Currently, manual testing is required:

1. Load the extension in development mode
2. Navigate to a Plex video
3. Test clip creation with buttons and shortcuts
4. Verify clips appear in ClipForge dashboard

## Troubleshooting

### Buttons not appearing
- Ensure you're on a Plex video page
- Refresh the page
- Check browser console for errors

### Authentication issues
- Verify ClipForge API is running
- Check the API URL in settings
- Try disconnecting and reconnecting

### Clips not creating
- Check that you're authenticated
- Verify the video is playing
- Check browser console for errors

## Security

- Tokens are stored securely using Chrome's storage API
- All API communication uses bearer token authentication
- Tokens are automatically refreshed when expired
- No sensitive data is logged to console

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
- Open an issue on GitHub
- Check the ClipForge documentation
- Visit the ClipForge dashboard for help