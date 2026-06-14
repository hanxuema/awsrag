// API endpoints constructed from dynamically injected API_BASE
const API_CHAT = `${API_BASE}/api/chat`;
const API_UPLOAD_URL = `${API_BASE}/api/upload-url`;
const API_DOCUMENTS = `${API_BASE}/api/documents`;

// State variables
let activeSources = [];

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadStatus = document.getElementById('upload-status');
const progressFill = document.getElementById('progress-fill');
const statusMessage = document.getElementById('status-message');
const documentsList = document.getElementById('documents-list');
const refreshDocsBtn = document.getElementById('refresh-docs-btn');

const chatBoard = document.getElementById('chat-board');
const chatForm = document.getElementById('chat-form');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const clearChatBtn = document.getElementById('clear-chat-btn');

const sourcesDrawer = document.getElementById('sources-drawer');
const closeDrawerBtn = document.getElementById('close-drawer-btn');
const drawerContent = document.getElementById('drawer-content');

// Helper: Format Markdown-like text to HTML
function formatResponse(text) {
    if (!text) return '';
    
    let formatted = text
        // Escape HTML
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // Code blocks: ```code```
        .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
        // Inline code: `code`
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold: **text** or __text__
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        // Italic: *text* or _text_
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/_([^_]+)_/g, '<em>$1</em>')
        // List items
        .replace(/^\s*[-*+]\s+(.+)$/gm, '<li>$1</li>')
        // Bullet wrappers
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        // Linebreaks
        .replace(/\n/g, '<br>');
        
    return formatted;
}

// 1. Documents Operations

// Fetch current documents from the serverless index
async function fetchDocuments() {
    try {
        const response = await fetch(API_DOCUMENTS);
        if (!response.ok) throw new Error('Failed to fetch document list');
        
        const data = await response.json();
        renderDocuments(data.documents || []);
    } catch (error) {
        console.error('Error fetching documents:', error);
    }
}

// Render document items in the sidebar
function renderDocuments(docs) {
    if (docs.length === 0) {
        documentsList.innerHTML = '<p class="empty-list-text">No documents indexed yet.</p>';
        return;
    }
    
    documentsList.innerHTML = docs.map(doc => {
        const sizeKb = doc.sizeChars ? (doc.sizeChars / 1024).toFixed(1) + ' KB' : '0 KB';
        const badgeClass = doc.status === 'indexed' ? 'doc-badge' : 'doc-badge indexing';
        const statusText = doc.status === 'indexed' ? 'Indexed' : 'Processing';
        
        return `
            <div class="doc-item">
                <div class="doc-row">
                    <div class="doc-name" title="${doc.filename}">${doc.filename}</div>
                    <button class="delete-btn" onclick="deleteDocument('${doc.filename}')" title="Delete document">🗑️</button>
                </div>
                <div class="doc-meta">
                    <span>${sizeKb} | ${doc.chunksCount} chunks</span>
                    <span class="${badgeClass}">${statusText}</span>
                </div>
            </div>
        `;
    }).join('');
}

// Delete document operation
window.deleteDocument = async function(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}" from the knowledge base?`)) {
        return;
    }
    try {
        const response = await fetch(`${API_DOCUMENTS}?filename=${filename}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Delete request failed');
        
        // Refresh list immediately
        await fetchDocuments();
        
        // Append system notification to chat board
        appendMessage('assistant', `🧹 Removed **${filename}** from the knowledge base.`);
    } catch (error) {
        console.error('Error deleting document:', error);
        alert(`Failed to delete document: ${error.message}`);
    }
};

// Start polling document indexing status
let pollInterval = null;
function startDocPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        await fetchDocuments();
        // Check if any documents are still in 'processing' status
        const processingDocs = document.querySelectorAll('.doc-badge.indexing');
        if (processingDocs.length === 0) {
            clearInterval(pollInterval);
            pollInterval = null;
            console.log("Polling stopped: all documents indexed.");
        }
    }, 4000);
}

// 2. Direct File Upload to S3

// Trigger file input dialog
dropZone.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

// Drag and drop event handlers
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
    }
});

// Direct upload implementation
async function handleFileUpload(file) {
    const filename = file.name;
    const contentType = file.type || 'application/octet-stream';
    
    // Reset and show progress UI
    uploadStatus.style.display = 'block';
    progressFill.style.width = '0%';
    statusMessage.innerText = 'Requesting S3 upload token...';
    
    try {
        // Step 1: Request presigned URL from API Gateway/Lambda
        const tokenResponse = await fetch(API_UPLOAD_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, contentType })
        });
        
        if (!tokenResponse.ok) {
            throw new Error(`Upload token request failed: ${tokenResponse.statusText}`);
        }
        
        const { uploadUrl, key } = await tokenResponse.json();
        
        statusMessage.innerText = 'Uploading directly to S3...';
        progressFill.style.width = '30%';
        
        // Step 2: Upload file blob directly to S3 bucket
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', uploadUrl, true);
        xhr.setRequestHeader('Content-Type', contentType);
        
        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                const percentComplete = 30 + Math.round((event.loaded / event.total) * 60);
                progressFill.style.width = `${percentComplete}%`;
            }
        };
        
        xhr.onload = async () => {
            if (xhr.status === 200) {
                progressFill.style.width = '100%';
                statusMessage.innerText = 'Uploaded! Processing and indexing...';
                
                // Refresh docs and start status polling to capture the "processing" state
                await fetchDocuments();
                startDocPolling();
                
                setTimeout(() => {
                    uploadStatus.style.display = 'none';
                }, 3000);
            } else {
                throw new Error(`Direct S3 upload failed with status code ${xhr.status}`);
            }
        };
        
        xhr.onerror = () => {
            throw new Error('Network error during file upload.');
        };
        
        xhr.send(file);
        
    } catch (error) {
        console.error('Upload Error:', error);
        progressFill.style.width = '0%';
        statusMessage.innerText = `Error: ${error.message}`;
        statusMessage.style.color = '#ef4444';
        
        setTimeout(() => {
            uploadStatus.style.display = 'none';
            statusMessage.style.color = '';
        }, 5000);
    }
}

// 3. Chat and Generation Operations

// Render messages on board
function appendMessage(sender, text, sources = null) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', `${sender}-message`);
    
    let contentHtml = `<div class="message-content"><p>${formatResponse(text)}</p>`;
    
    // If sources exist, format a sources container
    if (sources && sources.length > 0) {
        // Create an ID to identify this specific message source group
        const msgId = 'sources-' + Math.random().toString(36).substr(2, 9);
        
        contentHtml += `
            <div class="sources-container">
                <div class="sources-header" onclick="toggleSourcesList('${msgId}')">
                    🔍 Retrieved Citations (${sources.length}) ▾
                </div>
                <div id="${msgId}" class="sources-list">
                    ${sources.map((src, idx) => `
                        <button class="source-badge" onclick="openSourceDrawer(${idx})">
                            📄 ${src.doc_name} <span class="source-score">${src.similarity.toFixed(2)}</span>
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    contentHtml += '</div>';
    msgDiv.innerHTML = contentHtml;
    
    chatBoard.appendChild(msgDiv);
    chatBoard.scrollTop = chatBoard.scrollHeight;
}

// Toggle inline citations list visibility
window.toggleSourcesList = function(msgId) {
    const list = document.getElementById(msgId);
    if (list.style.display === 'none') {
        list.style.display = 'flex';
    } else {
        list.style.display = 'none';
    }
};

// Show a temporary typing indicator block
function showTypingIndicator() {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.id = 'typing-indicator';
    indicatorDiv.classList.add('message', 'assistant-message');
    indicatorDiv.innerHTML = `
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    chatBoard.appendChild(indicatorDiv);
    chatBoard.scrollTop = chatBoard.scrollHeight;
}

// Remove temporary typing indicator
function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

// Submit chat query
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;
    
    const topK = parseInt(document.getElementById('top-k').value) || 3;
    const temp = parseFloat(document.getElementById('temperature').value) || 0.2;
    
    // Disable inputs during inference
    queryInput.value = '';
    queryInput.disabled = true;
    sendBtn.disabled = true;
    
    // 1. Display User Message
    appendMessage('user', query);
    
    // 2. Show Typing Indicator
    showTypingIndicator();
    
    try {
        // 3. Request LLM Inference
        const response = await fetch(API_CHAT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: topK, temperature: temp })
        });
        
        removeTypingIndicator();
        
        if (!response.ok) {
            throw new Error(`Server returned error: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Save sources globally so that badges can trigger details in the side drawer
        activeSources = data.sources || [];
        
        // 4. Display Assistant Message with citations
        appendMessage('assistant', data.answer, data.sources);
        
    } catch (error) {
        removeTypingIndicator();
        console.error('Chat error:', error);
        appendMessage('assistant', `⚠️ Sorry, an error occurred: ${error.message}`);
    } finally {
        // Re-enable inputs
        queryInput.disabled = false;
        sendBtn.disabled = false;
        queryInput.focus();
    }
});

// 4. Source Drawer Operations

// Open the drawer on the right containing full texts of retrieved chunks
window.openSourceDrawer = function(index) {
    const source = activeSources[index];
    if (!source) return;
    
    drawerContent.innerHTML = `
        <div class="drawer-source-item">
            <div class="drawer-source-title">
                <span>📄 ${source.doc_name}</span>
                <span class="source-score">Match Score: ${source.similarity.toFixed(4)}</span>
            </div>
            <hr style="border: 0; border-top: 1px solid var(--border-glass); margin: 8px 0;">
            <p class="drawer-source-text">${source.text.replace(/\n/g, '<br>')}</p>
        </div>
    `;
    
    sourcesDrawer.style.display = 'flex';
};

// Close Drawer Action
closeDrawerBtn.addEventListener('click', () => {
    sourcesDrawer.style.display = 'none';
});

// Clear conversational history
clearChatBtn.addEventListener('click', () => {
    // Keep only the first welcome message
    chatBoard.innerHTML = '';
    appendMessage('assistant', 
        '🧹 Chat history cleared. Ready for new questions based on your indexed knowledge base.'
    );
});

// Refresh documents list manually
refreshDocsBtn.addEventListener('click', fetchDocuments);

// Initial Load Actions
window.addEventListener('DOMContentLoaded', () => {
    fetchDocuments();
    // If there are documents, poll immediately once just in case there are processing items
    startDocPolling();
});
