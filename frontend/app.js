// App Configuration - Chrome compatible
const API_BASE_URL = window.location.origin + '/api';

// State Management
let isLoading = false;
let messageHistory = [];

// DOM Elements
const elements = {
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    chatMessages: document.getElementById('chatMessages'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    schemaModal: document.getElementById('schemaModal'),
    schemaBtn: document.getElementById('schemaBtn'),
    closeSchemaModal: document.getElementById('closeSchemaModal'),
    clearBtn: document.getElementById('clearBtn'),
    statusIndicator: document.getElementById('statusIndicator'),
    statusText: document.getElementById('statusText'),
    errorToast: document.getElementById('errorToast'),
    schemaContent: document.getElementById('schemaContent'),
    exampleBtns: document.querySelectorAll('.example-btn')
};

// Initialize App
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    checkServerStatus();
    setWelcomeTime();
});

function initializeApp() {
    // Auto-resize textarea
    elements.messageInput.addEventListener('input', autoResizeTextarea);
    
    // Enable send button when there's text
    elements.messageInput.addEventListener('input', toggleSendButton);
    
    // Handle Enter key
    elements.messageInput.addEventListener('keydown', handleKeyDown);
    
    // Load message history from localStorage
    loadMessageHistory();
}

function setupEventListeners() {
    // Send message
    elements.sendBtn.addEventListener('click', sendMessage);
    
    // Schema modal
    elements.schemaBtn.addEventListener('click', showSchemaModal);
    elements.closeSchemaModal.addEventListener('click', hideSchemaModal);
    elements.schemaModal.addEventListener('click', function(e) {
        if (e.target === elements.schemaModal) {
            hideSchemaModal();
        }
    });
    
    // Clear chat
    elements.clearBtn.addEventListener('click', clearChat);
    
    // Example buttons
    elements.exampleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const question = this.getAttribute('data-question');
            elements.messageInput.value = question;
            autoResizeTextarea();
            toggleSendButton();
            sendMessage();
        });
    });
    
    // Error toast close
    const toastClose = elements.errorToast.querySelector('.toast-close');
    if (toastClose) {
        toastClose.addEventListener('click', hideErrorToast);
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + Enter to send message
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            if (!isLoading && elements.messageInput.value.trim()) {
                sendMessage();
            }
        }
        
        // Escape to close modal
        if (e.key === 'Escape') {
            if (elements.schemaModal.classList.contains('show')) {
                hideSchemaModal();
            }
            if (elements.errorToast.classList.contains('show')) {
                hideErrorToast();
            }
        }
    });
}

function autoResizeTextarea() {
    const textarea = elements.messageInput;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function toggleSendButton() {
    const hasText = elements.messageInput.value.trim().length > 0;
    elements.sendBtn.disabled = !hasText || isLoading;
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isLoading && elements.messageInput.value.trim()) {
            sendMessage();
        }
    }
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message || isLoading) return;
    
    // Add user message to chat
    addMessage(message, 'user');
    
    // Clear input
    elements.messageInput.value = '';
    autoResizeTextarea();
    toggleSendButton();
    
    // Add loading message to chat instead of overlay
    const loadingMessageId = addLoadingMessage();
    
    try {
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache',
            body: JSON.stringify({ question: message })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Remove loading message
        removeLoadingMessage(loadingMessageId);
        
        if (data.success) {
            addMessage(data.response, 'assistant', {
                executionTime: data.execution_time
            });
        } else {
            addMessage(data.error_message || 'Erro desconhecido', 'error');
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        // Remove loading message
        removeLoadingMessage(loadingMessageId);
        addMessage(`Erro de conexão: ${error.message}`, 'error');
        showErrorToast('Erro ao conectar com o servidor. Verifique se o servidor está rodando.');
        updateServerStatus(false);
    }
}

function addMessage(content, type = 'assistant', metadata = null) {
    const messageData = {
        content,
        type,
        timestamp: new Date().toISOString(),
        metadata
    };
    
    // Add to history
    messageHistory.push(messageData);
    saveMessageHistory();
    
    // Create message element
    const messageElement = createMessageElement(messageData);
    elements.chatMessages.appendChild(messageElement);
    
    // Scroll to bottom
    scrollToBottom();
}

function createMessageElement(messageData) {
    const { content, type, timestamp, metadata } = messageData;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Set avatar icon
    const icon = type === 'user' ? 'fas fa-user' : 
                 type === 'error' ? 'fas fa-exclamation-triangle' : 
                 'fas fa-robot';
    avatarDiv.innerHTML = `<i class="${icon}"></i>`;
    
    // Create message text
    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    
    if (type === 'error') {
        textDiv.innerHTML = `<strong>Erro:</strong> ${escapeHtml(content)}`;
    } else {
        textDiv.innerHTML = formatMessageContent(content);
    }
    
    // Create timestamp
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = formatTime(timestamp);
    
    // Add execution time if available
    if (metadata && metadata.executionTime) {
        timeDiv.innerHTML += ` • <i class="fas fa-clock"></i> ${metadata.executionTime.toFixed(2)}s`;
    }
    
    contentDiv.appendChild(textDiv);
    contentDiv.appendChild(timeDiv);
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    return messageDiv;
}

function formatMessageContent(content) {
    // Escape HTML first
    let formatted = escapeHtml(content);
    
    // Convert line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Format code blocks (simple detection)
    formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre style="background: #f1f5f9; padding: 0.75rem; border-radius: 6px; margin: 0.5rem 0; border-left: 4px solid var(--sus-primary); overflow-x: auto;"><code>$1</code></pre>');
    
    // Format inline code
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background: #f1f5f9; padding: 0.25rem 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.875em;">$1</code>');
    
    // Format bold text
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Format italic text
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    return formatted;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Agora';
    if (diffMins < 60) return `${diffMins}m atrás`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h atrás`;
    
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function scrollToBottom() {
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function addLoadingMessage() {
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant-message loading-message';
    loadingDiv.id = loadingId;
    
    loadingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="inline-loading">
                    <div class="inline-spinner">
                        <i class="fas fa-brain"></i>
                    </div>
                    <span>Processando sua consulta...</span>
                </div>
            </div>
        </div>
    `;
    
    elements.chatMessages.appendChild(loadingDiv);
    scrollToBottom();
    
    return loadingId;
}

function removeLoadingMessage(loadingId) {
    const loadingElement = document.getElementById(loadingId);
    if (loadingElement) {
        loadingElement.remove();
    }
}

function showLoading() {
    isLoading = true;
    elements.loadingOverlay.classList.add('show');
    toggleSendButton();
}

function hideLoading() {
    isLoading = false;
    elements.loadingOverlay.classList.remove('show');
    toggleSendButton();
}

async function showSchemaModal() {
    elements.schemaModal.classList.add('show');
    
    try {
        elements.schemaContent.textContent = 'Carregando esquema...';
        
        const response = await fetch(`${API_BASE_URL}/schema`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        elements.schemaContent.textContent = data.schema;
        
    } catch (error) {
        console.error('Error loading schema:', error);
        elements.schemaContent.textContent = `Erro ao carregar esquema: ${error.message}`;
        showErrorToast('Erro ao carregar o esquema do banco de dados');
    }
}

function hideSchemaModal() {
    elements.schemaModal.classList.remove('show');
}

function clearChat() {
    if (confirm('Tem certeza que deseja limpar toda a conversa? Esta ação não pode ser desfeita.')) {
        elements.chatMessages.innerHTML = '';
        messageHistory = [];
        saveMessageHistory();
        
        // Add welcome message back
        setTimeout(() => {
            addWelcomeMessage();
        }, 100);
    }
}

function addWelcomeMessage() {
    const welcomeMessage = {
        content: 'Olá! Sou o assistente inteligente do DataVisSUS. Estou aqui para ajudá-lo a consultar dados de saúde pública de forma simples e intuitiva.<br><br>Faça suas perguntas em linguagem natural sobre dados do SUS, mortalidade, recursos hospitalares, vacinação e muito mais!',
        type: 'assistant',
        timestamp: new Date().toISOString()
    };
    
    const messageElement = createMessageElement(welcomeMessage);
    elements.chatMessages.appendChild(messageElement);
    scrollToBottom();
}

function setWelcomeTime() {
    const welcomeTimeElement = document.getElementById('welcomeTime');
    if (welcomeTimeElement) {
        welcomeTimeElement.textContent = formatTime(new Date().toISOString());
    }
}

async function checkServerStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            updateServerStatus(true);
        } else {
            updateServerStatus(false);
        }
    } catch (error) {
        console.error('Server health check failed:', error);
        updateServerStatus(false);
    }
}

function updateServerStatus(isOnline) {
    const indicator = elements.statusIndicator.querySelector('i');
    const text = elements.statusText;
    
    if (isOnline) {
        indicator.style.color = '#10b981';
        text.textContent = 'Online';
        text.style.color = 'white';
    } else {
        indicator.style.color = '#ef4444';
        text.textContent = 'Offline';
        text.style.color = '#fecaca';
    }
}

function showErrorToast(message) {
    const errorText = document.getElementById('errorText');
    errorText.textContent = message;
    elements.errorToast.classList.add('show');
    
    // Auto hide after 5 seconds
    setTimeout(() => {
        hideErrorToast();
    }, 5000);
}

function hideErrorToast() {
    elements.errorToast.classList.remove('show');
}

function saveMessageHistory() {
    try {
        // Keep only last 50 messages to avoid localStorage limits
        const recentHistory = messageHistory.slice(-50);
        localStorage.setItem('chatHistory', JSON.stringify(recentHistory));
    } catch (error) {
        console.warn('Failed to save message history:', error);
    }
}

function loadMessageHistory() {
    try {
        const saved = localStorage.getItem('chatHistory');
        if (saved) {
            messageHistory = JSON.parse(saved);
            
            // Clear current messages and reload from history
            elements.chatMessages.innerHTML = '';
            
            messageHistory.forEach(messageData => {
                const messageElement = createMessageElement(messageData);
                elements.chatMessages.appendChild(messageElement);
            });
            
            scrollToBottom();
        } else {
            // Add welcome message if no history
            addWelcomeMessage();
        }
    } catch (error) {
        console.warn('Failed to load message history:', error);
        addWelcomeMessage();
    }
}

// Utility Functions
function debounce(func, wait) {
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

// Check server status periodically
setInterval(checkServerStatus, 30000); // Every 30 seconds

// Handle visibility change to reconnect when page becomes visible
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        checkServerStatus();
    }
});

// Export for potential future use
window.ChatApp = {
    sendMessage,
    clearChat,
    showSchemaModal,
    checkServerStatus
};