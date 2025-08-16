# ClipForge 🎬

ClipForge is a web-based video clipping application that allows you to create clips from your Plex media server sessions. Monitor what's currently playing, generate precise video clips with frame-accurate trimming, and manage your video collection through an intuitive web interface.

## Features

- **Live Session Monitoring**: Track active Plex media server sessions in real-time
- **Precise Video Clipping**: Create clips with second-accurate start/end times
- **Frame Preview**: Visual preview of start and end frames before creating clips
- **Video Editor**: Built-in video trimming and editing capabilities
- **Bulk Operations**: Select and manage multiple clips at once
- **Secure Authentication**: Token-based authentication with Plex integration
- **Quality Options**: Multiple output quality settings (Low, Medium, High)
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **Thumbnail Generation**: Automatic thumbnail creation for video previews

## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - Database ORM
- **Pydantic** - Data validation and settings management
- **FFmpeg** - Video processing and clip generation
- **JWT** - Authentication tokens
- **Structured Logging** - Comprehensive logging with correlation IDs

### Frontend
- **Vanilla JavaScript** - No heavy framework dependencies
- **Video.js** - Professional video player
- **CSS Grid/Flexbox** - Modern responsive layouts
- **Service Workers** - Progressive Web App capabilities

### Infrastructure
- **Docker** - Containerized deployment
- **SQLite** - Lightweight database
- **File-based Storage** - Direct file system storage for media

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Plex Media Server
- FFmpeg (included in Docker image)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/clipforge.git
   cd clipforge
   ```

2. **Configure Docker Compose**
   Create or modify `docker-compose.yml`:
   ```yaml
   services:
     clipforge:
       image: jonnike/clipforge:latest
       container_name: clipforge
       ports:
         - "8002:8002"
       environment:
         - CLIPFORGE_JWT_SECRET=generate_a_long(32char)_secure_string_for_this_value
         - CLIPFORGE_PLEX_SERVER_TOKEN=XXXXXXXXXXXXXXXXXXX
       volumes:
         # Persistent storage for clips, snapshots, thumbnails, and database
         - /volumes/clipforge:/app/static
         - /media:/media
       restart: unless-stopped
       healthcheck:
         test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8002/api/health', timeout=5)"]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 40s
   ```

3. **Set environment variables**
   ```bash
   # Generate a secure JWT secret (minimum 32 characters)
   openssl rand -base64 32
   
   # Get your Plex server token from Plex settings
   # Replace these in docker-compose.yml
   https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token
   ```

4. **Run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

5. **Access the application**
   - Open your browser to `http://localhost:8002`
   - Log in with your Plex credentials

### Manual Installation

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install FFmpeg**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # macOS
   brew install ffmpeg
   ```

3. **Run the application**
   ```bash
   python3 backend/main.py
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLIPFORGE_JWT_SECRET` | JWT signing secret (required) | None |
| `CLIPFORGE_PLEX_SERVER_NAME` | Your Plex server name | None |
| `CLIPFORGE_PORT` | Application port | 8002 |
| `CLIPFORGE_HOST` | Application host | 0.0.0.0 |

### Docker Volumes

- `/app/static` - Persistent storage for clips, snapshots, and database
- `/media` - Mount your media files for processing

## Usage

### Creating Clips

1. **Monitor Sessions**: View active Plex sessions on the Create tab
2. **Set Time Range**: Enter start and end times or use the current time buttons
3. **Preview Selection**: Generate frame previews to verify your selection
4. **Create Clip**: Process the video clip with your chosen quality settings
5. **Download**: Access your clips through the View tab

### Video Editing

1. **Open Editor**: Click the edit button on any existing clip
2. **Set Markers**: Use the video timeline to set new start/end points
3. **Preview Trim**: Review your edits before processing
4. **Process**: Generate the edited clip

### Bulk Management

1. **Enable Bulk Mode**: Click "Bulk Select" in the View tab
2. **Select Clips**: Choose multiple clips for batch operations
3. **Bulk Delete**: Remove multiple clips at once

## Development

### Project Structure

```
clipforge/
├── backend/                 # FastAPI backend
│   ├── api/                # API endpoints and middleware
│   ├── core/               # Configuration and utilities
│   ├── domain/             # Domain models and interfaces
│   ├── infrastructure/     # Database and external services
│   └── services/           # Business logic services
├── frontend/               # Static web frontend
│   ├── static/
│   │   ├── css/           # Stylesheets
│   │   └── js/            # JavaScript modules
│   ├── index.html         # Main application
│   └── login.html         # Authentication page
├── clips/                  # Generated video clips
├── docker-compose.yml      # Docker configuration
└── requirements.txt        # Python dependencies
```

### Development Commands

```bash
# Run linting and type checking
./lint.sh

# Start development server
python3 backend/main.py

# Clean up snapshots
./cleanup_snapshots.sh
```

## Deployment

### Production Deployment

1. **Configure environment**
   ```bash
   # Use strong JWT secret
   CLIPFORGE_JWT_SECRET=$(openssl rand -base64 32)
   
   # Set your Plex server details
   CLIPFORGE_PLEX_SERVER_NAME="Your Production Plex Server"
   ```

2. **Set up volumes**
   ```bash
   # Create persistent storage
   mkdir -p /data/clipforge/{clips,snapshots,thumbnails,db}
   
   # Update docker-compose.yml volumes
   volumes:
     - /data/clipforge:/app/static
     - /path/to/your/media:/media:ro
   ```

3. **Deploy with Docker**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

### Health Monitoring

The application includes health checks at `/api/health` and Docker health monitoring.

## Security

- **Authentication**: Secure Plex-based authentication
- **Authorization**: Token-based access control with media access tokens
- **CSRF Protection**: Built-in CSRF middleware
- **Input Validation**: Comprehensive request validation
- **Security Headers**: Proper security headers configuration

## Known Limitations

- Videos longer than a few minutes may require extra processing time
- Large file processing is handled synchronously (async queue planned)
- Mobile video editing has limited functionality

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow the existing code style and architecture patterns
- Add tests for new functionality
- Update documentation for user-facing changes
- Ensure all linting checks pass

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Report bugs and feature requests on GitHub Issues
- **Community**: Join discussions in GitHub Discussions

## Roadmap

- [ ] Async task queue with Redis
- [ ] Progressive Web App (PWA) support
- [ ] Advanced editing features (text overlays, transitions, millisecond choice)
- [ ] Subtitle support
- [ ] Automated testing suite
