
# DataVisSUS - Professional Web Interface

A modern, professional web interface for the DataVisSUS TXT2SQL Agent, built with Node.js/Express backend and vanilla JavaScript frontend.

## ✨ Features

- **Modern Design**: Clean, professional interface with SUS branding
- **Real-time Chat**: Interactive chat interface with message history
- **Database Schema Viewer**: Built-in modal to view database structure
- **Auto-completion**: Example queries with one-click execution
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Performance**: Optimized with compression, caching, and rate limiting
- **Security**: Helmet.js security headers and CORS protection

## 🚀 Quick Start

### Prerequisites

- Node.js (v16+)
- Python 3.8+
- Ollama with llama3 model
- Existing DataVisSUS project setup

### Installation

1. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

2. **Ensure Python environment is set up:**
   ```bash
   # Your existing Python environment should have all required packages
   python3 -c "from src.application.container.dependency_injection import DependencyContainer; print('✅ Python environment OK')"
   ```

3. **Start the server:**
   ```bash
   # Production mode
   npm start
   
   # Development mode (with auto-reload)
   npm run dev
   ```

4. **Open your browser:**
   ```
   http://localhost:3000
   ```

## 📁 Project Structure

```
├── index.html          # Main HTML file
├── styles.css          # Modern CSS with CSS Grid/Flexbox
├── app.js             # Frontend JavaScript application
├── server.js          # Node.js/Express backend server
├── python_bridge.py   # Python bridge connecting to existing architecture
├── package.json       # Node.js dependencies and scripts
└── WEB_INTERFACE_README.md
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file (optional):

```env
NODE_ENV=production
PORT=3000
HOST=0.0.0.0
```

### Server Configuration

The server includes:

- **Rate Limiting**: 100 requests per 15 minutes (general), 10 queries per minute
- **Security Headers**: Helmet.js with CSP
- **CORS**: Configured for local development
- **Compression**: Gzip compression enabled
- **Static Files**: Served with caching headers

### Python Bridge

The `python_bridge.py` script connects to your existing Python architecture:

- Uses the same `DependencyContainer` and services
- Maintains all existing functionality
- Handles errors gracefully
- Supports JSON communication

## 🎨 Interface Features

### Chat Interface
- **Message History**: Persistent chat history in localStorage
- **Auto-resize**: Input field automatically expands
- **Keyboard Shortcuts**: Enter to send, Ctrl+Enter for new line
- **Message Formatting**: Support for code blocks and markdown-like formatting
- **Timestamps**: Relative time display (e.g., "2m ago")

### Schema Viewer
- **Modal Dialog**: Clean modal interface for database schema
- **Formatted Display**: Syntax-highlighted schema information
- **Responsive**: Works on all screen sizes

### Example Queries
- **One-click Examples**: Pre-built queries for common use cases
- **Health Data Focus**: Queries specific to SUS health data
- **Visual Indicators**: Icons and clear categorization

### Status Indicators
- **Server Status**: Real-time connection status
- **Loading States**: Clear loading indicators during processing
- **Error Handling**: User-friendly error messages

## 🔌 API Endpoints

### POST `/api/query`
Process a natural language query.

**Request:**
```json
{
  "question": "Qual é cidade com mais morte de homens?"
}
```

**Response:**
```json
{
  "success": true,
  "response": "Based on the data analysis...",
  "execution_time": 2.34,
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### GET `/api/schema`
Get database schema information.

**Response:**
```json
{
  "schema": "CREATE TABLE...",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### GET `/api/health`
Server health check.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "uptime": 3600,
  "environment": "development"
}
```

## 🛠️ Development

### Running in Development Mode

```bash
# Install nodemon for auto-reload
npm install -g nodemon

# Start with auto-reload
npm run dev
```

### Testing the Python Bridge

```bash
# Test query processing
python3 python_bridge.py query "Quantos leitos de UTI existem?"

# Test schema retrieval
python3 python_bridge.py schema

# Test health check
python3 python_bridge.py health
```

### Frontend Development

The frontend uses vanilla JavaScript with modern ES6+ features:

- **Modules**: Organized code structure
- **Async/Await**: Modern asynchronous programming
- **Fetch API**: HTTP requests
- **LocalStorage**: Client-side data persistence
- **CSS Grid/Flexbox**: Modern layout techniques
- **CSS Custom Properties**: Theming system

## 🎯 Advantages Over Flask Version

1. **Better Performance**:
   - Node.js async handling
   - Built-in compression
   - Static file caching
   - Connection pooling

2. **Modern UI/UX**:
   - Responsive design
   - Better animations
   - Professional styling
   - Mobile-first approach

3. **Enhanced Security**:
   - Helmet.js security headers
   - Rate limiting
   - Input validation
   - CORS protection

4. **Developer Experience**:
   - Hot reload in development
   - Better error handling
   - Structured logging
   - Environment configuration

5. **Scalability**:
   - Process separation (Node.js + Python)
   - Better resource management
   - Configurable timeouts
   - Health monitoring

## 🔒 Security Features

- **Content Security Policy**: Prevents XSS attacks
- **Rate Limiting**: Prevents abuse and DoS attacks
- **Input Validation**: Sanitizes all user inputs
- **Error Handling**: Doesn't expose sensitive information
- **HTTPS Ready**: Easy SSL/TLS configuration

## 📱 Mobile Support

The interface is fully responsive and mobile-friendly:

- **Touch Optimized**: Large touch targets
- **Responsive Layout**: Adapts to all screen sizes
- **Mobile Navigation**: Collapsible sidebar
- **Fast Loading**: Optimized for mobile networks

## 🚦 Production Deployment

For production deployment:

1. **Set environment variables:**
   ```bash
   export NODE_ENV=production
   export PORT=80
   ```

2. **Use a process manager:**
   ```bash
   # Using PM2
   npm install -g pm2
   pm2 start server.js --name datavissus-web
   ```

3. **Set up reverse proxy (Nginx):**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://localhost:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

## 🆘 Troubleshooting

### Common Issues

1. **Python bridge fails:**
   - Check Python path and dependencies
   - Verify database file exists
   - Ensure Ollama is running

2. **Port already in use:**
   ```bash
   # Change port in server.js or use environment variable
   PORT=3001 npm start
   ```

3. **CORS errors:**
   - Check origin configuration in server.js
   - Verify frontend URL matches CORS settings

4. **Rate limiting:**
   - Check if requests exceed limits
   - Adjust rate limiting settings if needed

### Logs

The server provides detailed logging:
- Request/response timing
- Error messages with stack traces
- Python bridge communication
- Health check status

## 📈 Performance Monitoring

Monitor your application with:

- **Response Times**: Built-in execution time tracking
- **Error Rates**: Comprehensive error logging
- **Request Volume**: Rate limiting metrics
- **Memory Usage**: Node.js process monitoring

---

**Created by**: DataVisSUS Team  
**Technology Stack**: Node.js, Express, Vanilla JavaScript, Python  
**License**: MIT