# ClipForge - Claude Instructions

ClipForge is a FastAPI-based web application for creating video clips from Plex media server sessions. It integrates with Plex for authentication and media access, uses FFmpeg for video processing, and provides a responsive web interface for clip management.

## Project Architecture

### Backend (FastAPI + Python 3)
- **Domain-driven design** with clear separation of concerns
- **API Layer**: endpoints, middleware, validation  
- **Core**: configuration, security, logging, exceptions
- **Domain**: schemas, interfaces, business models
- **Infrastructure**: database, repositories
- **Services**: business logic (auth, clips, Plex integration)

### Frontend (Vanilla JS)
- Modern JavaScript with Video.js player
- Responsive CSS Grid/Flexbox layouts
- Service worker for PWA capabilities

## Development Guidelines

### Code Standards
- Always use `python3` to run Python code
- Follow the existing linting configuration: run `./lint.sh` before committing
- Maintain comprehensive type hints using Pydantic models
- Follow Black formatting (100 char line length), Flake8, isort, and MyPy standards
- Use structured logging with correlation IDs

### Security Requirements
- **NEVER** expose JWT secrets, Plex tokens, or authentication credentials
- Maintain secure file handling for video processing operations
- Follow existing security patterns in `backend/core/security.py`
- Validate all user inputs, especially file paths and time parameters
- Use the established CSRF protection and rate limiting

### File Organization
- **PREFER** editing existing modules over creating new files
- Follow the established directory structure:
  - `backend/api/` - HTTP endpoints and middleware
  - `backend/core/` - cross-cutting concerns (config, security, logging)
  - `backend/domain/` - business models and interfaces
  - `backend/infrastructure/` - data access and external integrations
  - `backend/services/` - business logic implementation
- Maintain the SQLAlchemy models and Pydantic schemas separation

### Video Processing
- Test video processing changes with small clips first to avoid long processing times
- Respect FFmpeg parameter validation and security constraints
- Handle video processing errors gracefully with proper logging
- Consider file size limits and processing timeouts

### Plex Integration
- Validate Plex authentication flows when making auth-related changes
- Respect Plex API rate limits and authentication tokens
- Test session monitoring functionality with active Plex sessions
- Handle Plex server connectivity issues gracefully

### Database & Storage
- Use SQLAlchemy ORM patterns consistently
- Maintain database migrations if schema changes are needed
- Respect the file system storage structure for clips, snapshots, and thumbnails
- Handle storage cleanup and retention policies

### Docker & Deployment
- Respect volume mappings: `/app/static` for persistent data, `/media` for source files
- Maintain health check endpoints at `/api/health`
- Test container builds before deployment
- Ensure environment variables are properly configured

### Testing & Validation
- Run `./lint.sh` to validate code quality before committing
- Test authentication flows with valid Plex credentials
- Verify video processing with sample clips
- Check responsive design on multiple screen sizes
- Validate API endpoints with proper error handling

### Performance Considerations
- Video processing is currently synchronous - be mindful of processing times
- Consider file sizes when testing clip generation
- Monitor memory usage during video operations
- Use appropriate caching strategies for Plex data

## Common Tasks

### Adding New API Endpoints
1. Define schemas in `backend/domain/schemas.py`
2. Add endpoint in appropriate `backend/api/v1/` module
3. Implement business logic in `backend/services/`
4. Update authentication/authorization as needed
5. Test with proper error cases

### Video Processing Changes
1. Modify `backend/services/clip_service.py`
2. Test with small clips first
3. Validate FFmpeg parameter security
4. Update error handling and logging

### Frontend Updates
1. Follow existing CSS and JS patterns
2. Maintain Video.js integration
3. Test responsive behavior
4. Ensure service worker compatibility

## Security Notes
- All video processing parameters are validated for security
- File paths are sanitized to prevent directory traversal
- JWT tokens have appropriate expiry times
- Rate limiting is enforced on API endpoints
- CORS is configured for the expected frontend domains