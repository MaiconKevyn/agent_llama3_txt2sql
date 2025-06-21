#!/usr/bin/env node

/**
 * DataVisSUS Web Interface Server
 * Professional Node.js/Express server for TXT2SQL Agent
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// App Configuration
const app = express();
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';
const PYTHON_SCRIPT_PATH = path.join(__dirname, '..', 'python_bridge.py');

// Security Middleware - Enhanced Chrome compatibility
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com", "https://fonts.googleapis.com"],
            fontSrc: ["'self'", "https://cdnjs.cloudflare.com", "https://fonts.gstatic.com"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'", `http://localhost:${PORT}`, `http://127.0.0.1:${PORT}`]
        },
        useDefaults: false
    },
    crossOriginEmbedderPolicy: false,
    contentTypeOptions: false // Disable for Chrome compatibility
}));

// Enhanced CORS Configuration for Chrome compatibility
app.use(cors({
    origin: function(origin, callback) {
        // Allow requests with no origin (mobile apps, Postman, etc.)
        if (!origin) return callback(null, true);
        
        const allowedOrigins = process.env.NODE_ENV === 'production'
            ? ['https://your-domain.com']
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

// MELHORADO: Static Files com Headers corretos
app.use(express.static(__dirname, {
    maxAge: process.env.NODE_ENV === 'production' ? '1y' : '0',
    etag: true,
    lastModified: true,
    setHeaders: (res, filePath) => {
        // Headers específicos para CSS
        if (filePath.endsWith('.css')) {
            res.setHeader('Content-Type', 'text/css; charset=utf-8');
            res.setHeader('Cache-Control', 'no-cache'); // ADICIONADO para debug
        }
        if (filePath.endsWith('.js')) {
            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
        }
        if (filePath.endsWith('.html')) {
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
        }
    }
}));

// Enhanced CSS route for Chrome compatibility
app.get('/styles.css', (req, res) => {
    const cssPath = path.join(__dirname, 'styles.css');

    // Verificar se arquivo existe
    if (!fs.existsSync(cssPath)) {
        console.error('❌ CSS file not found:', cssPath);
        return res.status(404).send('CSS file not found');
    }

    // Enhanced headers for Chrome
    res.setHeader('Content-Type', 'text/css; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    
    // Send file
    res.sendFile(cssPath, (err) => {
        if (err) {
            console.error('❌ Error serving CSS:', err);
        } else {
            console.log('✅ CSS file served successfully');
        }
    });
});

app.get('/app.js', (req, res) => {
    const jsPath = path.join(__dirname, 'app.js');

    if (!fs.existsSync(jsPath)) {
        console.error('❌ JS file not found:', jsPath);
        return res.status(404).send('JS file not found');
    }

    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
    res.sendFile(jsPath);

    console.log('✅ JS file served successfully');
});

// Health Check Endpoint
app.get('/api/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        environment: process.env.NODE_ENV || 'development'
    });
});

// Query Processing Endpoint
app.post('/api/query', async (req, res) => {
    const startTime = Date.now();

    try {
        const { question } = req.body;

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

        // Execute Python script with the question
        const result = await executePythonQuery(question);

        const executionTime = (Date.now() - startTime) / 1000;

        console.log(`[${new Date().toISOString()}] Query completed in ${executionTime.toFixed(2)}s`);

        res.json({
            ...result,
            execution_time: executionTime,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        const executionTime = (Date.now() - startTime) / 1000;

        console.error(`[${new Date().toISOString()}] Query error:`, error);

        res.status(500).json({
            success: false,
            error_message: error.message || 'Internal server error',
            execution_time: executionTime,
            timestamp: new Date().toISOString()
        });
    }
});

// Schema Endpoint
app.get('/api/schema', async (req, res) => {
    try {
        console.log(`[${new Date().toISOString()}] Schema request received`);

        const result = await executePythonSchema();

        res.json({
            ...result,
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

// Serve main page
app.get('/', (req, res) => {
    const htmlPath = path.join(__dirname, 'index.html');

    if (!fs.existsSync(htmlPath)) {
        console.error('❌ HTML file not found:', htmlPath);
        return res.status(404).send('HTML file not found');
    }

    res.sendFile(htmlPath);
});

// ADICIONADO: Debug route para verificar arquivos
app.get('/debug/files', (req, res) => {
    const files = {
        'styles.css': fs.existsSync(path.join(__dirname, 'styles.css')),
        'app.js': fs.existsSync(path.join(__dirname, 'app.js')),
        'index.html': fs.existsSync(path.join(__dirname, 'index.html')),
        'python_bridge.py': fs.existsSync(PYTHON_SCRIPT_PATH)
    };

    res.json({
        files,
        __dirname,
        PYTHON_SCRIPT_PATH
    });
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
 * Execute Python query via child process
 */
function executePythonQuery(question) {
    return new Promise((resolve, reject) => {
        const python = spawn('python3', [PYTHON_SCRIPT_PATH, 'query', question], {
            cwd: path.dirname(PYTHON_SCRIPT_PATH),
            env: { ...process.env, NO_COLOR: '1', TERM: 'dumb' },
            stdio: ['pipe', 'pipe', 'ignore'] // Ignore stderr to suppress warnings
        });

        let stdout = '';

        python.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        python.on('close', (code) => {
            if (code !== 0) {
                reject(new Error(`Python script failed with code ${code}`));
                return;
            }

            try {
                const result = JSON.parse(stdout);
                resolve(result);
            } catch (parseError) {
                reject(new Error(`Failed to parse Python response: ${parseError.message}`));
            }
        });

        python.on('error', (error) => {
            reject(new Error(`Failed to spawn Python process: ${error.message}`));
        });

        // Set timeout
        setTimeout(() => {
            python.kill('SIGTERM');
            reject(new Error('Query timeout - please try again'));
        }, 120000); // 2 minutes timeout
    });
}

/**
 * Execute Python schema request via child process
 */
function executePythonSchema() {
    return new Promise((resolve, reject) => {
        const python = spawn('python3', [PYTHON_SCRIPT_PATH, 'schema'], {
            cwd: path.dirname(PYTHON_SCRIPT_PATH),
            env: { ...process.env, NO_COLOR: '1', TERM: 'dumb' },
            stdio: ['pipe', 'pipe', 'ignore'] // Ignore stderr to suppress warnings
        });

        let stdout = '';

        python.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        python.on('close', (code) => {
            if (code !== 0) {
                reject(new Error(`Python script failed with code ${code}`));
                return;
            }

            try {
                const result = JSON.parse(stdout);
                resolve(result);
            } catch (parseError) {
                reject(new Error(`Failed to parse Python response: ${parseError.message}`));
            }
        });

        python.on('error', (error) => {
            reject(new Error(`Failed to spawn Python process: ${error.message}`));
        });

        // Set timeout
        setTimeout(() => {
            python.kill('SIGTERM');
            reject(new Error('Schema request timeout'));
        }, 30000); // 30 seconds timeout
    });
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
    console.log(`📍 Server: http://${HOST}:${PORT}`);
    console.log(`🌐 Environment: ${process.env.NODE_ENV || 'development'}`);
    console.log(`📁 Static files: ${__dirname}`);
    console.log(`🐍 Python bridge: ${PYTHON_SCRIPT_PATH}`);
    console.log(`🔍 Debug files: http://${HOST}:${PORT}/debug/files`);
    console.log('⏹️  Press Ctrl+C to stop');
    console.log('='.repeat(50));

    // Check critical files
    const criticalFiles = ['styles.css', 'app.js', 'index.html'];
    criticalFiles.forEach(file => {
        const filePath = path.join(__dirname, file);
        if (fs.existsSync(filePath)) {
            console.log(`✅ ${file} found`);
        } else {
            console.error(`❌ ${file} NOT FOUND at ${filePath}`);
        }
    });

    // Check if Python bridge exists
    if (!fs.existsSync(PYTHON_SCRIPT_PATH)) {
        console.warn(`⚠️  Python bridge not found: ${PYTHON_SCRIPT_PATH}`);
        console.warn('   Make sure to create the Python bridge script');
    } else {
        console.log('✅ Python bridge found');
    }
});