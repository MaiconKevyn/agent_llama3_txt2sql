#!/usr/bin/env node

/**
 * DataVisSUS Web Interface Server
 * Interface web independente que se comunica com o TXT2SQL Agent via API REST
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const path = require('path');
const fs = require('fs');
require('dotenv').config();

const API_CONFIG = require('./config/api');

// App Configuration
const app = express();
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';
const DIST_PATH = path.join(__dirname, 'dist');
const LEGACY_PUBLIC_PATH = path.join(__dirname, 'public');
const STATIC_PATH = fs.existsSync(path.join(DIST_PATH, 'index.html'))
    ? DIST_PATH
    : LEGACY_PUBLIC_PATH;
const USING_LEGACY_PUBLIC = STATIC_PATH === LEGACY_PUBLIC_PATH;
const LEGACY_STYLE_SOURCES = USING_LEGACY_PUBLIC ? ["https://cdnjs.cloudflare.com"] : [];
const LEGACY_FONT_SOURCES = USING_LEGACY_PUBLIC ? ["https://cdnjs.cloudflare.com"] : [];
const LEGACY_SCRIPT_SOURCES = USING_LEGACY_PUBLIC ? ["https://cdn.jsdelivr.net"] : [];
const SAFE_AGENT_ERROR_MESSAGE = 'Nao foi possivel processar sua consulta com seguranca. Tente refinar o recorte ou pedir o grafico de outra forma.';
const INTERNAL_AGENT_ERROR_PATTERNS = [
    /SEMANTIC PLAN ERROR/i,
    /CHART PLAN ERROR/i,
    /Binder Error/i,
    /Catalog Error/i,
    /Parser Error/i,
    /Traceback/i,
    /sqlalchemy/i,
    /duckdb/i,
    /KeyError/i,
    /ValueError/i,
    /Internal Server Error/i
];

function sanitizeAgentError(message) {
    if (!message) return message;
    return INTERNAL_AGENT_ERROR_PATTERNS.some((pattern) => pattern.test(message))
        ? SAFE_AGENT_ERROR_MESSAGE
        : message;
}

// Security Middleware - Enhanced Chrome compatibility
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", ...LEGACY_STYLE_SOURCES],
            fontSrc: ["'self'", "https://fonts.gstatic.com", ...LEGACY_FONT_SOURCES],
            scriptSrc: ["'self'", ...LEGACY_SCRIPT_SOURCES],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'", `http://localhost:${PORT}`, `http://127.0.0.1:${PORT}`, API_CONFIG.BASE_URL]
        },
        useDefaults: false
    },
    crossOriginEmbedderPolicy: false,
    contentTypeOptions: false
}));

// Enhanced CORS Configuration
app.use(cors({
    origin: function(origin, callback) {
        // Allow requests with no origin (mobile apps, Postman, etc.)
        if (!origin) return callback(null, true);
        
        const allowedOrigins = process.env.NODE_ENV === 'production'
            ? process.env.ALLOWED_ORIGINS?.split(',') || []
            : [
                'http://localhost:3000',
                'http://127.0.0.1:3000',
                'http://0.0.0.0:3000',
                `http://localhost:${PORT}`,
                `http://127.0.0.1:${PORT}`,
                `http://0.0.0.0:${PORT}`
            ];
        
        if (allowedOrigins.includes(origin)) {
            return callback(null, true);
        }
        
        // For development, allow any localhost origin
        if (process.env.NODE_ENV !== 'production' && origin.startsWith('http://localhost')) {
            return callback(null, true);
        }
        
        callback(new Error('Not allowed by CORS'));
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'Accept', 'Origin'],
    exposedHeaders: ['Content-Length', 'X-Kuma-Revision'],
    maxAge: 86400 // 24 hours
}));

// Rate Limiting
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100, // limit each IP to 100 requests per windowMs
    message: {
        error: 'Too many requests from this IP, please try again later.'
    },
    standardHeaders: true,
    legacyHeaders: false,
});

const queryLimiter = rateLimit({
    windowMs: 1 * 60 * 1000, // 1 minute
    max: 10, // limit each IP to 10 queries per minute
    message: {
        error: 'Too many queries from this IP, please try again later.'
    }
});

app.use('/api/', limiter);
app.use('/api/query', queryLimiter);

// Middleware
app.use(compression());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Static Files with correct headers
app.use(express.static(STATIC_PATH, {
    maxAge: '0',
    etag: true,
    lastModified: true,
    setHeaders: (res, filePath) => {
        const distAssetsPath = path.join(DIST_PATH, 'assets') + path.sep;
        const isDistAsset = STATIC_PATH === DIST_PATH && filePath.startsWith(distAssetsPath);

        if (filePath.endsWith('.css')) {
            res.setHeader('Content-Type', 'text/css; charset=utf-8');
        }
        if (filePath.endsWith('.js')) {
            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
        }
        if (filePath.endsWith('.html')) {
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.setHeader('Cache-Control', 'no-cache');
            return;
        }
        if (isDistAsset) {
            res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
            return;
        }
        res.setHeader('Cache-Control', 'no-cache');
    }
}));

app.get('/favicon.ico', (req, res) => {
    res.status(204).end();
});

// Health Check Endpoint
app.get('/api/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        environment: process.env.NODE_ENV || 'development',
        agent_api: API_CONFIG.BASE_URL
    });
});

// Query Processing Endpoint - Proxy to Agent API
app.post('/api/query', async (req, res) => {
    const startTime = Date.now();

    try {
        const { question, session_id, debug, table_context, chart_from_last_result } = req.body;
        const debugEnabled = Boolean(debug);

        if (!question || typeof question !== 'string' || question.trim().length === 0) {
            return res.status(400).json({
                success: false,
                error_message: 'Question is required and must be a non-empty string',
                timestamp: new Date().toISOString()
            });
        }

        if (question.length > 1000) {
            return res.status(400).json({
                success: false,
                error_message: 'Question is too long (maximum 1000 characters)',
                timestamp: new Date().toISOString()
            });
        }

        console.log(`[${new Date().toISOString()}] Processing query: "${question.substring(0, 100)}${question.length > 100 ? '...' : ''}"`);

        // Forward request to Agent API
        const response = await forwardToAgentAPI(API_CONFIG.ENDPOINTS.QUERY, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                query: question,
                session_id: session_id || null,
                include_sql: debugEnabled,
                debug: debugEnabled,
                chart_from_last_result: Boolean(chart_from_last_result),
                table_context: table_context || null
            })
        });

        const executionTime = (Date.now() - startTime) / 1000;

        console.log(`[${new Date().toISOString()}] Query completed in ${executionTime.toFixed(2)}s`);

        res.json({
            success: Boolean(response.success),
            status: response.status,
            response: sanitizeAgentError(response.response || response.answer),
            answer: sanitizeAgentError(response.answer || response.response),
            error_message: sanitizeAgentError(response.error_message || (!response.success ? response.answer || response.response : null)),
            sql_query: response.sql_query || response.sql || null,
            sql: response.sql || response.sql_query || null,
            chart: response.chart || null,
            session_id: response.session_id || session_id || null,
            metadata: debugEnabled ? response.metadata || {} : {},
            debug: debugEnabled ? response.debug || null : null,
            execution_time: executionTime,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        const executionTime = (Date.now() - startTime) / 1000;

        console.error(`[${new Date().toISOString()}] Query error:`, error);

        res.status(500).json({
            success: false,
            error_message: sanitizeAgentError(error.message || 'Internal server error') || SAFE_AGENT_ERROR_MESSAGE,
            execution_time: executionTime,
            timestamp: new Date().toISOString()
        });
    }
});

// Schema Endpoint - Proxy to Agent API
app.get('/api/schema', async (req, res) => {
    try {
        console.log(`[${new Date().toISOString()}] Schema request received`);

        const selectedTable = typeof req.query.table === 'string' ? req.query.table.trim() : '';
        const schemaEndpoint = selectedTable
            ? `${API_CONFIG.ENDPOINTS.SCHEMA}?table=${encodeURIComponent(selectedTable)}`
            : API_CONFIG.ENDPOINTS.SCHEMA;

        const response = await forwardToAgentAPI(schemaEndpoint, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        res.json({
            ...response,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Schema error:`, error);

        res.status(500).json({
            error: error.message || 'Failed to load schema',
            timestamp: new Date().toISOString()
        });
    }
});

// Models Endpoint - Proxy to Agent API
app.get('/api/models', async (req, res) => {
    try {
        const response = await forwardToAgentAPI(API_CONFIG.ENDPOINTS.MODELS, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        res.json(response);

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Models error:`, error);

        res.status(500).json({
            error: error.message || 'Failed to load models',
            timestamp: new Date().toISOString()
        });
    }
});

// Local database overview endpoint - proxy to Agent API
app.get('/api/database/overview', async (req, res) => {
    try {
        const response = await forwardToAgentAPI(API_CONFIG.ENDPOINTS.DATABASE_OVERVIEW, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        res.json(response);

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Database overview error:`, error);

        res.status(500).json({
            error: error.message || 'Failed to load database overview',
            timestamp: new Date().toISOString()
        });
    }
});

// Local database table endpoint - proxy to Agent API
app.get('/api/database/table/:schema/:table', async (req, res) => {
    try {
        const schemaName = encodeURIComponent(req.params.schema);
        const tableName = encodeURIComponent(req.params.table);
        const limit = req.query.limit ? `?limit=${encodeURIComponent(req.query.limit)}` : '';
        const endpoint = `${API_CONFIG.ENDPOINTS.DATABASE_TABLE}/${schemaName}/${tableName}${limit}`;

        const response = await forwardToAgentAPI(endpoint, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        res.json(response);

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Database table error:`, error);

        res.status(500).json({
            error: error.message || 'Failed to load database table',
            timestamp: new Date().toISOString()
        });
    }
});

// Local database read-only query endpoint - proxy to Agent API
app.post('/api/database/query', queryLimiter, async (req, res) => {
    try {
        const response = await forwardToAgentAPI(API_CONFIG.ENDPOINTS.DATABASE_QUERY, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                sql: req.body.sql,
                limit: req.body.limit
            })
        });

        res.json(response);

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Database query error:`, error);

        res.status(500).json({
            error: sanitizeAgentError(error.message || 'Failed to execute database query'),
            timestamp: new Date().toISOString()
        });
    }
});

// Agent Health Check Endpoint
app.get('/api/agent-health', async (req, res) => {
    try {
        const response = await forwardToAgentAPI(API_CONFIG.ENDPOINTS.HEALTH, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        res.json({
            agent_status: 'online',
            agent_health: response,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        res.json({
            agent_status: 'offline',
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

// Serve main page
app.get('/', (req, res) => {
    const htmlPath = path.join(STATIC_PATH, 'index.html');

    if (!fs.existsSync(htmlPath)) {
        console.error('❌ HTML file not found:', htmlPath);
        return res.status(404).send('HTML file not found');
    }

    res.sendFile(htmlPath);
});

// Debug endpoint to check configuration
app.get('/debug/config', (req, res) => {
    const files = {
        'dist/index.html': fs.existsSync(path.join(DIST_PATH, 'index.html')),
        'public/index.html': fs.existsSync(path.join(LEGACY_PUBLIC_PATH, 'index.html')),
        static_path: STATIC_PATH
    };

    res.json({
        files,
        config: {
            api_base_url: API_CONFIG.BASE_URL,
            port: PORT,
            host: HOST,
            dist_path: DIST_PATH,
            public_path: LEGACY_PUBLIC_PATH,
            static_path: STATIC_PATH,
            environment: process.env.NODE_ENV || 'development'
        },
        timestamp: new Date().toISOString()
    });
});

// SPA fallback for client-side routes
app.get(/^\/(?!(api|debug)(\/|$)).*/, (req, res) => {
    const htmlPath = path.join(STATIC_PATH, 'index.html');
    if (fs.existsSync(htmlPath)) {
        return res.sendFile(htmlPath);
    }
    return res.status(404).json({ error: 'Endpoint not found', path: req.originalUrl, timestamp: new Date().toISOString() });
});

// 404 handler
app.use('*', (req, res) => {
    console.log('❌ 404 - Not found:', req.originalUrl);
    res.status(404).json({
        error: 'Endpoint not found',
        path: req.originalUrl,
        timestamp: new Date().toISOString()
    });
});

// Error handler
app.use((err, req, res, next) => {
    console.error(`[${new Date().toISOString()}] Server error:`, err);

    res.status(500).json({
        error: 'Internal server error',
        timestamp: new Date().toISOString()
    });
});

/**
 * Forward requests to Agent API with retry logic
 */
async function forwardToAgentAPI(endpoint, options = {}) {
    const url = `${API_CONFIG.BASE_URL}${endpoint}`;
    const maxAttempts = API_CONFIG.RETRY.MAX_ATTEMPTS;
    let delay = API_CONFIG.RETRY.DELAY;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUTS.QUERY);
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`Agent API returned ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            clearTimeout(timeoutId);
            console.error(`[Attempt ${attempt}/${maxAttempts}] Error connecting to Agent API:`, error.message);

            if (attempt === maxAttempts) {
                throw new Error(`Agent API unavailable after ${maxAttempts} attempts. Please ensure the TXT2SQL Agent is running on ${API_CONFIG.BASE_URL}`);
            }

            // Wait before retry
            await new Promise(resolve => setTimeout(resolve, delay));
            delay *= API_CONFIG.RETRY.BACKOFF_MULTIPLIER;
        }
    }
}

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n[SERVER] Received SIGINT. Graceful shutdown...');
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log('\n[SERVER] Received SIGTERM. Graceful shutdown...');
    process.exit(0);
});

// Start server
app.listen(PORT, HOST, () => {
    console.log('\n🚀 DataVisSUS Web Interface Server Started');
    console.log('='.repeat(50));
    console.log(`📍 Web Interface: http://${HOST}:${PORT}`);
    console.log(`🔗 Agent API: ${API_CONFIG.BASE_URL}`);
    console.log(`🌐 Environment: ${process.env.NODE_ENV || 'development'}`);
    console.log(`📁 Static files: ${STATIC_PATH}`);
    console.log(`📦 Vite dist: ${DIST_PATH}`);
    console.log(`📂 Legacy public: ${LEGACY_PUBLIC_PATH}`);
    console.log(`🔍 Debug config: http://${HOST}:${PORT}/debug/config`);
    console.log('⏹️  Press Ctrl+C to stop');
    console.log('='.repeat(50));

    // Check frontend files without requiring legacy assets when a Vite build exists.
    const distIndexPath = path.join(DIST_PATH, 'index.html');
    const publicIndexPath = path.join(LEGACY_PUBLIC_PATH, 'index.html');
    const hasDistIndex = fs.existsSync(distIndexPath);

    console.log('\n📋 Checking frontend files:');
    if (hasDistIndex) {
        console.log(`✅ dist/index.html found at ${distIndexPath}`);
        if (fs.existsSync(publicIndexPath)) {
            console.log(`ℹ️  public/index.html fallback available at ${publicIndexPath}`);
        }
    } else {
        console.warn(`⚠️  dist/index.html not found at ${distIndexPath}`);
        ['index.html', 'app.js', 'styles.css'].forEach(file => {
            const filePath = path.join(LEGACY_PUBLIC_PATH, file);
            if (fs.existsSync(filePath)) {
                console.log(`✅ public/${file} found`);
            } else {
                console.error(`❌ public/${file} NOT FOUND at ${filePath}`);
            }
        });
    }

    console.log('\n🔌 Testing Agent API connection...');
    forwardToAgentAPI(API_CONFIG.ENDPOINTS.HEALTH)
        .then(() => {
            console.log('✅ Agent API connection successful');
        })
        .catch((error) => {
            console.warn(`⚠️  Agent API connection failed: ${error.message}`);
            console.warn('   Make sure the TXT2SQL Agent is running on port 8000');
        });
});
