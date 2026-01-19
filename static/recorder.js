let mediaRecorder;
let chunks = [];
let isRecording = false;
let isPaused = false;
let currentStream = null;
let recordingStartTime = null;
let recordedBlob = null;

// WebSocket connection
let socket = null;
let sessionId = null;

// Voice call state - WebSocket streaming
let isInCall = false;
let callMediaRecorder = null;
let callStream = null;
let audioContext = null;
let analyser = null;
let microphone = null;
let callChunkInterval = null;
let silenceTimeout = null;
let currentCallChunks = [];
let isRecordingSpeech = false;
let isProcessingChunk = false;
let speechStartTime = null;
let lastTranscriptionTime = 0;
let currentAudioQueue = []; // Queue for streaming audio chunks

const recordBtn = document.getElementById("record-btn");
const sendBtn = document.getElementById("send-btn");
const messageInput = document.getElementById("message-input");
const statusEl = document.getElementById("status");
const chatContainer = document.getElementById("chat-container");
const emptyState = document.getElementById("empty-state");
const callBtn = document.getElementById("call-btn");
const callStatus = document.getElementById("call-status");
const callStatusText = document.getElementById("call-status-text");
const container = document.querySelector(".container");

function setStatus(text) {
    statusEl.textContent = text;
}

function setRecordingState(state) {
    // state: 'idle', 'recording', 'paused', 'preview'
    isRecording = (state === 'recording' || state === 'paused');
    isPaused = (state === 'paused');
    
    if (state === 'recording') {
        recordBtn.classList.add("recording");
        recordBtn.innerHTML = "⏹ Stop";
    } else if (state === 'paused') {
        recordBtn.classList.remove("recording");
        recordBtn.innerHTML = "▶ Resume";
    } else if (state === 'preview') {
        recordBtn.classList.remove("recording");
        recordBtn.innerHTML = "🎤 Record";
        showPreviewControls();
    } else {
        recordBtn.classList.remove("recording");
        recordBtn.innerHTML = "🎤 Record";
        hidePreviewControls();
    }
    recordBtn.disabled = false;
}

function showPreviewControls() {
    // Show preview audio player and send/cancel buttons
    const inputArea = document.querySelector('.input-area');
    
    // Remove existing preview if any
    const existingPreview = document.getElementById('preview-controls');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    const previewDiv = document.createElement('div');
    previewDiv.id = 'preview-controls';
    previewDiv.className = 'preview-controls';
    
    // Title
    const title = document.createElement('div');
    title.className = 'preview-title';
    title.textContent = 'Review your recording';
    
    const audioPreview = document.createElement('audio');
    audioPreview.id = 'preview-audio';
    audioPreview.controls = true;
    audioPreview.src = URL.createObjectURL(recordedBlob);
    
    const btnGroup = document.createElement('div');
    btnGroup.className = 'preview-buttons';
    
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'cancel-voice-btn';
    cancelBtn.className = 'cancel-voice-btn';
    cancelBtn.type = 'button';
    cancelBtn.innerHTML = '✕ Cancel';
    
    const sendBtn = document.createElement('button');
    sendBtn.id = 'send-voice-btn';
    sendBtn.className = 'send-voice-btn';
    sendBtn.type = 'button';
    sendBtn.innerHTML = '✓ Send';
    
    btnGroup.appendChild(cancelBtn);
    btnGroup.appendChild(sendBtn);
    
    previewDiv.appendChild(title);
    previewDiv.appendChild(audioPreview);
    previewDiv.appendChild(btnGroup);
    
    // Insert before input-wrapper
    const inputWrapper = document.querySelector('.input-wrapper');
    inputArea.insertBefore(previewDiv, inputWrapper);
}

function hidePreviewControls() {
    const preview = document.getElementById('preview-controls');
    if (preview) {
        preview.remove();
    }
    recordedBlob = null;
}

function addMessage(text, isUser, options = {}) {
    // Options: { isCallMessage: false, isSystemMessage: false }
    const { isCallMessage = false, isSystemMessage = false } = options;
    
    // Hide empty state if it exists
    if (emptyState) {
        emptyState.style.display = "none";
    }
    
    // System messages (call started/ended) - centered
    if (isSystemMessage) {
        const systemDiv = document.createElement("div");
        systemDiv.className = "system-message";
        systemDiv.innerHTML = `<span class="system-message-text">${text}</span>`;
        chatContainer.appendChild(systemDiv);
        
        // Scroll to bottom smoothly
        chatContainer.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
        });
        return;
    }
    
    // Create message element
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user" : "assistant"}`;
    if (isCallMessage) {
        messageDiv.classList.add("call-message");
    }
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text;
    
    // Add call icon if this is a call message
    if (isCallMessage) {
        const callIcon = document.createElement("span");
        callIcon.className = "call-indicator";
        callIcon.innerHTML = "📞";
        callIcon.title = "Voice Call Message";
        bubble.appendChild(callIcon);
    }
    
    const time = document.createElement("div");
    time.className = "message-time";
    const now = new Date();
    time.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    bubble.appendChild(time);
    messageDiv.appendChild(bubble);
    chatContainer.appendChild(messageDiv);
    
    // Scroll to bottom smoothly
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
    });
}

function addVoiceMessage(audioUrl, isUser, messageId, transcription = null) {
    // Hide empty state if it exists
    if (emptyState) {
        emptyState.style.display = "none";
    }
    
    // Create message element
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user" : "assistant"}`;
    messageDiv.setAttribute("data-message-id", messageId);
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble voice-message";
    
    // Create audio element
    const audio = document.createElement("audio");
    audio.id = `audio_${messageId}`;
    audio.src = audioUrl;
    audio.preload = "auto";  // Changed to "auto" for better loading
    audio.crossOrigin = "anonymous";  // Always set CORS for proxy URLs
    
    // Force load metadata
    audio.load();
    
    // Voice controls container
    const voiceControls = document.createElement("div");
    voiceControls.className = "voice-controls";
    
    // Play/pause button
    const playBtn = document.createElement("button");
    playBtn.className = "play-pause-btn";
    playBtn.innerHTML = "▶";
    playBtn.setAttribute("aria-label", "Play");
    
    // Waveform visualizer (simple bars)
    const waveform = document.createElement("div");
    waveform.className = "waveform-visualizer";
    for (let i = 0; i < 20; i++) {
        const bar = document.createElement("div");
        bar.className = "waveform-bar";
        waveform.appendChild(bar);
    }
    
    // Duration display
    const duration = document.createElement("span");
    duration.className = "duration";
    duration.textContent = "0:00";
    
    // Update duration when metadata is loaded
    audio.addEventListener("loadedmetadata", () => {
        if (audio.duration && isFinite(audio.duration)) {
            const mins = Math.floor(audio.duration / 60);
            const secs = Math.floor(audio.duration % 60);
            duration.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        } else {
            // If duration is not available, try to load it
            audio.load();
        }
    });
    
    // Also try on canplay event (fallback)
    audio.addEventListener("canplay", () => {
        if (audio.duration && isFinite(audio.duration) && duration.textContent === "0:00") {
            const mins = Math.floor(audio.duration / 60);
            const secs = Math.floor(audio.duration % 60);
            duration.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        }
    });
    
    // Handle audio load errors
    let hasLoadError = false;
    audio.addEventListener("error", (e) => {
        console.error("Audio load error:", e, audio.error);
        hasLoadError = true;
        duration.textContent = "Error";
        playBtn.innerHTML = "⚠";
        playBtn.className = "play-pause-btn error";
        playBtn.title = "Audio failed to load. Click to retry.";
        duration.className = "duration error";
    });
    
    // Play/pause functionality
    let isPlaying = false;
    playBtn.addEventListener("click", async () => {
        if (isPlaying) {
            audio.pause();
            playBtn.innerHTML = "▶";
            bubble.classList.remove("playing");
            isPlaying = false;
        } else {
            try {
                // If there was a previous error, try to reload
                if (hasLoadError) {
                    audio.load();
                    hasLoadError = false;
                    playBtn.className = "play-pause-btn";
                    duration.className = "duration";
                    playBtn.title = "";
                }
                
                // Ensure audio is loaded before playing
                if (audio.readyState < 2) {  // HAVE_CURRENT_DATA
                    audio.load();
                    await new Promise((resolve, reject) => {
                        const timeout = setTimeout(() => reject(new Error("Timeout")), 5000);
                        audio.addEventListener("canplay", () => {
                            clearTimeout(timeout);
                            resolve();
                        }, { once: true });
                        audio.addEventListener("error", (err) => {
                            clearTimeout(timeout);
                            hasLoadError = true;
                            playBtn.className = "play-pause-btn error";
                            duration.className = "duration error";
                            reject(new Error("Audio load error"));
                        }, { once: true });
                    });
                }
                await audio.play();
                playBtn.innerHTML = "⏸";
                playBtn.className = "play-pause-btn";
                bubble.classList.add("playing");
                isPlaying = true;
                hasLoadError = false;
            } catch (err) {
                console.error("Error playing audio:", err);
                playBtn.innerHTML = "⚠";
                playBtn.className = "play-pause-btn error";
                duration.textContent = "Error";
                duration.className = "duration error";
                hasLoadError = true;
            }
        }
    });
    
    audio.addEventListener("ended", () => {
        playBtn.innerHTML = "▶";
        bubble.classList.remove("playing");
        isPlaying = false;
    });
    
    audio.addEventListener("pause", () => {
        playBtn.innerHTML = "▶";
        bubble.classList.remove("playing");
        isPlaying = false;
    });
    
    audio.addEventListener("play", () => {
        bubble.classList.add("playing");
    });
    
    // Assemble controls
    voiceControls.appendChild(playBtn);
    voiceControls.appendChild(waveform);
    voiceControls.appendChild(duration);
    
    bubble.appendChild(audio);
    bubble.appendChild(voiceControls);
    
    // Transcribe button (Instagram-style) - for both user and assistant
    const transcribeBtn = document.createElement("button");
    transcribeBtn.className = "transcribe-btn";
    transcribeBtn.innerHTML = "📝";
    transcribeBtn.setAttribute("data-message-id", messageId);
    transcribeBtn.title = "Show/Hide Transcription";
    transcribeBtn.type = "button";
    transcribeBtn.style.display = "inline-flex";
    transcribeBtn.style.visibility = "visible";
    transcribeBtn.style.opacity = "1";
    transcribeBtn.style.pointerEvents = "auto";
    
    const transcriptionDiv = document.createElement("div");
    transcriptionDiv.className = "transcription";
    transcriptionDiv.style.display = "none"; // Hidden by default
    
    // Store transcription in button data attribute for easy access
    if (transcription && transcription.trim()) {
        transcriptionDiv.textContent = transcription;
        transcribeBtn.setAttribute("data-has-transcription", "true");
    } else {
        transcribeBtn.setAttribute("data-has-transcription", "false");
    }
    
    transcribeBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        const isCurrentlyVisible = transcriptionDiv.style.display !== "none" && 
                                   transcriptionDiv.style.display !== "";
        
        if (!isCurrentlyVisible) {
            // Need to show transcription
            const hasTranscription = transcribeBtn.getAttribute("data-has-transcription") === "true" &&
                                    transcriptionDiv.textContent && 
                                    transcriptionDiv.textContent.trim() !== "";
            
            if (!hasTranscription) {
                // Need to fetch transcription
                transcribeBtn.innerHTML = "⏳";
                transcribeBtn.disabled = true;
                try {
                    const res = await fetch(`/transcribe/${messageId}`, {
                        method: "POST"
                    });
                    const data = await res.json();
                    if (data.transcription && data.transcription.trim()) {
                        transcriptionDiv.textContent = data.transcription;
                        transcribeBtn.setAttribute("data-has-transcription", "true");
                        transcriptionDiv.style.display = "block";
                        transcriptionDiv.classList.add("show");
                        transcribeBtn.innerHTML = "📝";
                        transcribeBtn.classList.add("active");
                    } else if (data.error) {
                        transcriptionDiv.textContent = "Could not transcribe audio";
                        transcriptionDiv.style.display = "block";
                        transcriptionDiv.classList.add("show");
                        transcribeBtn.innerHTML = "📝";
                    } else {
                        transcribeBtn.innerHTML = "📝";
                    }
                } catch (err) {
                    console.error("Transcription error:", err);
                    transcriptionDiv.textContent = "Error transcribing audio";
                    transcriptionDiv.style.display = "block";
                    transcriptionDiv.classList.add("show");
                    transcribeBtn.innerHTML = "📝";
                }
                transcribeBtn.disabled = false;
            } else {
                // Already have transcription, just show it
                transcriptionDiv.style.display = "block";
                transcriptionDiv.classList.add("show");
                transcribeBtn.classList.add("active");
            }
        } else {
            // Hide transcription
            transcriptionDiv.style.display = "none";
            transcriptionDiv.classList.remove("show");
            transcribeBtn.classList.remove("active");
        }
    });
    
    // Add transcribe button and transcription before timestamp
    bubble.appendChild(transcribeBtn);
    bubble.appendChild(transcriptionDiv);
    
    // Timestamp
    const time = document.createElement("div");
    time.className = "message-time";
    const now = new Date();
    time.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    bubble.appendChild(time);
    
    // Ensure transcribe button is always visible
    transcribeBtn.style.display = "inline-flex";
    
    messageDiv.appendChild(bubble);
    chatContainer.appendChild(messageDiv);
    
    // Scroll to bottom smoothly
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
    });
}

function showTypingIndicator() {
    if (emptyState) {
        emptyState.style.display = "none";
    }
    
    const typingDiv = document.createElement("div");
    typingDiv.className = "message assistant";
    typingDiv.id = "typing-indicator";
    
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.innerHTML = "<span></span><span></span><span></span>";
    
    typingDiv.appendChild(indicator);
    chatContainer.appendChild(typingDiv);
    
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
    });
}

function hideTypingIndicator() {
    const indicator = document.getElementById("typing-indicator");
    if (indicator) {
        indicator.remove();
    }
}

async function startRecording() {
    try {
        hidePreviewControls();
        currentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(currentStream, { mimeType: "audio/webm" });
        chunks = [];
        recordingStartTime = Date.now();

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                chunks.push(e.data);
            }
        };

        mediaRecorder.onstop = () => {
            if (chunks.length > 0) {
                recordedBlob = new Blob(chunks, { type: "audio/webm" });
                setRecordingState('preview');
                setStatus("");
            } else {
                setRecordingState('idle');
                setStatus("");
            }
            
            // Stop all tracks to release microphone
            if (currentStream) {
                currentStream.getTracks().forEach(track => track.stop());
                currentStream = null;
            }
        };

        mediaRecorder.start();
        setRecordingState('recording');
        setStatus("Recording... Tap Stop when done");
    } catch (err) {
        console.error("Microphone error:", err);
        
        let errorMessage = "Microphone permission denied or unavailable";
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
            errorMessage = "Please allow microphone access. Click the lock icon in the address bar and enable microphone permissions.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            errorMessage = "No microphone found. Please connect a microphone and try again.";
        }
        
        setStatus(errorMessage);
        // Don't add duplicate error messages - only show in status
        setRecordingState('idle');
    }
}

function pauseRecording() {
    if (mediaRecorder && isRecording && !isPaused) {
        mediaRecorder.pause();
        setRecordingState('paused');
        setStatus("Recording paused");
    }
}

function resumeRecording() {
    if (mediaRecorder && isPaused) {
        mediaRecorder.resume();
        setRecordingState('recording');
        setStatus("Recording...");
    }
}

function stopRecording() {
    if (mediaRecorder && (isRecording || isPaused)) {
        mediaRecorder.stop();
        // State will be set to 'preview' in onstop handler
    } else if (isPaused) {
        // If paused, stop it
        if (mediaRecorder) {
            mediaRecorder.stop();
        }
    }
}

function cancelRecording() {
    if (mediaRecorder && (isRecording || isPaused)) {
        mediaRecorder.stop();
    }
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
        currentStream = null;
    }
    chunks = [];
    recordedBlob = null;
    setRecordingState('idle');
    setStatus("");
    hidePreviewControls();
}

async function sendVoiceMessage() {
    if (!recordedBlob) {
        return;
    }
    
    const blob = recordedBlob;
    hidePreviewControls();
    setStatus("Sending...");
    
    try {
        const formData = new FormData();
        formData.append("audio", blob, "voice_message.webm");

        showTypingIndicator();

        const res = await fetch("/voice-message", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        hideTypingIndicator();
        
        if (data.error) {
            setStatus("Error: " + data.error);
            addMessage("Error: " + data.error, false);
            return;
        }
        
        // Add user voice message
        if (data.audio_url) {
            addVoiceMessage(data.audio_url, true, data.message_id, data.transcription);
        }
        
        // Generate and show AI response (pass detected language)
        if (data.transcription) {
            await generateAIResponse(data.transcription, data.message_id, data.language || "en");
        }
        
        setStatus("");
        recordedBlob = null;
        chunks = [];
    } catch (err) {
        hideTypingIndicator();
        setStatus("Error sending voice message");
        addMessage("Error: Failed to send voice message", false);
        console.error(err);
    }
}

async function generateAIResponse(transcription, user_message_id, language = "en") {
    showTypingIndicator();
    setStatus("Jarvis is responding...");
    
    try {
        const res = await fetch("/ai-response", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ 
                transcription: transcription,
                message_id: user_message_id,
                language: language  // Pass detected language
            }),
        });
        
        const data = await res.json();
        hideTypingIndicator();
        
        // Debug: Log response to see what we're getting
        console.log("AI Response data:", data);
        
        // Only treat as error if status is not 2xx OR if explicit error field exists
        if (res.status < 200 || res.status >= 300) {
            setStatus("Error: " + (data.error || "Failed to get response"));
            addMessage(data.error || "Error: Failed to get AI response", false);
            return;
        }
        
        // Check for explicit error in response
        if (data.error && data.error !== false) {
            setStatus("Error: " + data.error);
            addMessage(data.error, false);
            return;
        }
        
        // Check if it's an error message in the text
        if (data.text && (data.text.startsWith("⚠️") || data.text.startsWith("Sorry, I encountered an error") || data.text.startsWith("Sorry, I've reached"))) {
            addMessage(data.text, false);
            if (data.text.includes("API") || data.text.includes("quota")) {
                setStatus("API limit reached");
            }
            return;
        }
        
        // Add AI voice response (with text as transcription)
        // Check if we have valid text (not just "true" or empty)
        const responseText = data.text && typeof data.text === 'string' && data.text.trim() !== "" && data.text.trim().toLowerCase() !== "true" 
            ? data.text 
            : "";
        
        if (data.audio_url && data.audio_url.trim() !== "") {
            // We have audio - show voice message with transcription
            addVoiceMessage(data.audio_url, false, data.message_id, responseText);
            
            // Auto-play AI voice response with proper loading
            setTimeout(async () => {
                const audioElement = document.getElementById(`audio_${data.message_id}`);
                if (audioElement) {
                    try {
                        // Ensure audio is loaded before playing
                        if (audioElement.readyState < 2) {
                            audioElement.load();
                            await new Promise((resolve, reject) => {
                                const timeout = setTimeout(() => reject(new Error("Timeout")), 5000);
                                audioElement.addEventListener("canplay", () => {
                                    clearTimeout(timeout);
                                    resolve();
                                }, { once: true });
                                audioElement.addEventListener("error", () => {
                                    clearTimeout(timeout);
                                    reject(new Error("Audio load error"));
                                }, { once: true });
                            });
                        }
                        await audioElement.play();
                    } catch (err) {
                        console.log("Auto-play blocked or failed:", err);
                        // User interaction required - that's fine, they can click play
                    }
                }
            }, 800); // Slightly longer delay to ensure audio is loaded
        } else if (responseText) {
            // Fallback: if no audio but we have text, show text message
            addMessage(responseText, false);
        } else {
            // No audio and no valid text - show error
            console.error("No audio or text in response:", data);
            addMessage("Error: No response received from AI", false);
        }
        
        setStatus("");
    } catch (err) {
        hideTypingIndicator();
        setStatus("Error getting AI response");
        addMessage("Error: Failed to connect to server", false);
        console.error(err);
    }
}

// Text chat functionality
async function sendTextMessage() {
    const message = messageInput.value.trim();
    if (!message) {
        return;
    }
    
    // Add user message immediately
    addMessage(message, true);
    messageInput.value = "";
    
    // Show typing indicator
    showTypingIndicator();
    setStatus("Sending...");
    
    try {
        const res = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message: message }),
        });
        
        const data = await res.json();
        
        // Hide typing indicator
        hideTypingIndicator();
        
        if (data.error) {
            setStatus("Error: " + data.error);
            addMessage("Error: " + data.error, false);
            return;
        }
        
        // Add assistant response
        if (data.jarvis && data.jarvis.trim()) {
            addMessage(data.jarvis, false);
        }
        
        setStatus("");
    } catch (err) {
        hideTypingIndicator();
        setStatus("Error sending message");
        addMessage("Error: Failed to send message", false);
        console.error(err);
    }
}

// Event listeners
recordBtn.addEventListener("click", () => {
    if (isRecording && !isPaused) {
        // Currently recording, stop it
        stopRecording();
    } else if (isPaused) {
        // Currently paused, resume
        resumeRecording();
    } else if (document.getElementById('preview-controls')) {
        // Preview is showing, start new recording
        cancelRecording();
        setTimeout(() => startRecording(), 100);
    } else {
        // Idle, start recording
        startRecording();
    }
});

// Preview controls event listeners (delegated to document)
document.addEventListener('click', (e) => {
    if (e.target.id === 'send-voice-btn' || e.target.closest('#send-voice-btn')) {
        e.preventDefault();
        e.stopPropagation();
        sendVoiceMessage();
    } else if (e.target.id === 'cancel-voice-btn' || e.target.closest('#cancel-voice-btn')) {
        e.preventDefault();
        e.stopPropagation();
        cancelRecording();
    }
});

sendBtn.addEventListener("click", sendTextMessage);

messageInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendTextMessage();
    }
});

// Update record button text
setRecordingState(false);

// Load conversation history on page load
async function loadConversationHistory() {
    try {
        // Show loading indicator
        if (emptyState) {
            emptyState.style.display = "block";
            emptyState.textContent = "Loading conversation...";
        }
        
        const response = await fetch("/conversation-history");
        const data = await response.json();
        
        if (data.messages && data.messages.length > 0) {
            // Hide empty state
            if (emptyState) {
                emptyState.style.display = "none";
            }
            
            // Render all messages (batch render for better performance)
            data.messages.forEach((msg) => {
                if (msg.type === "voice") {
                    // Voice message - always use /audio/<message_id> for proxy
                    const audioUrl = msg.audio_url && msg.audio_url.startsWith("/audio/") 
                        ? msg.audio_url 
                        : `/audio/${msg.message_id}`;
                    addVoiceMessage(audioUrl, msg.role === "user", msg.message_id, msg.content || null);
                } else {
                    // Text message
                    addMessage(msg.content || "", msg.role === "user");
                }
            });
            
            // Scroll to bottom
            setTimeout(() => {
                chatContainer.scrollTo({
                    top: chatContainer.scrollHeight,
                    behavior: 'auto'
                });
            }, 100);
        } else {
            // No messages, show empty state
            if (emptyState) {
                emptyState.style.display = "block";
                emptyState.textContent = "No messages yet. Start a conversation!";
            }
        }
    } catch (error) {
        console.error("Error loading conversation history:", error);
        // Show empty state on error
        if (emptyState) {
            emptyState.style.display = "block";
            emptyState.textContent = "No messages yet. Start a conversation!";
        }
    }
}

// Voice Call Functions - WebSocket streaming with RAW PCM
// IMPORTANT: Deepgram Voice Agent requires LINEAR16 PCM at 48kHz
let pcmAudioContext = null;
let pcmSourceNode = null;
let pcmProcessorNode = null;
const PCM_SAMPLE_RATE = 48000; // Deepgram Voice Agent requires 48kHz

async function startVoiceCall() {
    try {
        // Check WebSocket connection
        if (!socket || !socket.connected) {
            setStatus("Connecting to server...");
            
            // Wait for connection with timeout
            const connectionPromise = new Promise((resolve, reject) => {
                if (socket && socket.connected) {
                    resolve();
                    return;
                }
                
                const timeout = setTimeout(() => {
                    reject(new Error("Connection timeout - Make sure app.py is running"));
                }, 5000);
                
                socket.once('connect', () => {
                    clearTimeout(timeout);
                    resolve();
                });
                
                socket.once('connect_error', (error) => {
                    clearTimeout(timeout);
                    reject(new Error("Server not available - Run 'python app.py'"));
                });
            });
            
            await connectionPromise;
            
            if (!socket || !socket.connected) {
                throw new Error("Could not connect to server. Make sure app.py is running.");
            }
        }
        
        // Get microphone permission - Request 48kHz for Voice Agent
        callStream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: PCM_SAMPLE_RATE,
                channelCount: 1
            }
        });
        
        // Start call on server
        socket.emit('start_call', { session_id: sessionId });
        
        // Create AudioContext for raw PCM capture at 48kHz
        pcmAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: PCM_SAMPLE_RATE
        });
        
        // Create source node from microphone stream
        pcmSourceNode = pcmAudioContext.createMediaStreamSource(callStream);
        
        // Use ScriptProcessorNode for raw PCM capture (4096 buffer size)
        // Note: ScriptProcessorNode is deprecated but works reliably across browsers
        // AudioWorklet is newer but has more complex setup
        const bufferSize = 4096;
        pcmProcessorNode = pcmAudioContext.createScriptProcessor(bufferSize, 1, 1);
        
        // Process audio and send raw PCM to server
        pcmProcessorNode.onaudioprocess = (e) => {
            if (!isInCall || !socket || !socket.connected) return;
            
            // Get Float32 audio data from input channel
            const float32Data = e.inputBuffer.getChannelData(0);
            
            // Convert Float32 [-1.0, 1.0] to Int16 [-32768, 32767] (Linear16)
            const int16Data = new Int16Array(float32Data.length);
            for (let i = 0; i < float32Data.length; i++) {
                // Clamp and scale
                const s = Math.max(-1, Math.min(1, float32Data[i]));
                int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            // Convert Int16Array to base64 for socket.io
            const uint8Data = new Uint8Array(int16Data.buffer);
            const base64Audio = btoa(String.fromCharCode.apply(null, uint8Data));
            
            // Send raw PCM to server (not WebM!)
            socket.emit('pcm_audio_chunk', {
                session_id: sessionId,
                audio: base64Audio,
                sample_rate: PCM_SAMPLE_RATE
            });
        };
        
        // Connect: microphone -> processor -> destination (needed for ScriptProcessor to work)
        pcmSourceNode.connect(pcmProcessorNode);
        pcmProcessorNode.connect(pcmAudioContext.destination);
        
        // Also create analyser for visualizations (optional)
        if (!audioContext) {
            audioContext = pcmAudioContext;
            analyser = audioContext.createAnalyser();
            analyser.fftSize = 2048;
            pcmSourceNode.connect(analyser);
        }
        
        isInCall = true;
        currentAudioQueue = [];
        
        // Update UI
        callBtn.classList.add("active");
        callBtn.innerHTML = "📞";
        callBtn.title = "End Voice Call";
        callStatus.classList.add("active");
        callStatusText.textContent = "Voice call active - Speak naturally...";
        container.classList.add("in-call");
        setStatus("Voice call started - Speak when ready");
        
        console.log("[Voice Call] Started with PCM capture at " + PCM_SAMPLE_RATE + "Hz");
        
    } catch (err) {
        console.error("Error starting call:", err);
        
        let errorMessage = "Failed to start call";
        
        // Check error type
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
            errorMessage = "Please allow microphone access. Click the lock icon in the address bar and enable microphone permissions.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            errorMessage = "No microphone found. Please connect a microphone and try again.";
        } else if (err.message && err.message.includes("connect")) {
            errorMessage = err.message; // Use connection error message
        } else if (err.message) {
            errorMessage = err.message;
        }
        
        setStatus(errorMessage);
        isInCall = false;
        
        // Reset UI
        callBtn.classList.remove("active");
        callStatus.classList.remove("active");
        container.classList.remove("in-call");
    }
}

// Voice Activity Detection - detects when user starts/stops speaking
function startVAD() {
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const threshold = 25; // Lowered threshold for better speech detection (was 30)
    const silenceDuration = 1200; // Wait 1.2 seconds of silence before processing (was 1.5s - faster response)
    
    function checkVoiceActivity() {
        if (!isInCall || !analyser) return;
        
        analyser.getByteFrequencyData(dataArray);
        
        // Calculate average volume
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        const average = sum / bufferLength;
        
        if (average > threshold) {
            // Speech detected!
            if (!isRecordingSpeech) {
                // Start recording with timeslices to collect data continuously
                isRecordingSpeech = true;
                speechStartTime = Date.now();
                currentCallChunks = []; // Reset chunks for new speech
                
                // Start MediaRecorder with 100ms timeslices (collects data every 100ms)
                if (callMediaRecorder.state === 'inactive') {
                    try {
                        callMediaRecorder.start(100); // 100ms timeslices for continuous data collection
                        callStatusText.textContent = "Listening...";
                        setStatus("Listening...");
                        console.log("🎤 Speech detected - recording started");
                    } catch (err) {
                        console.error("Error starting MediaRecorder:", err);
                        isRecordingSpeech = false;
                    }
                }
            }
            
            // Clear silence timeout
            if (silenceTimeout) {
                clearTimeout(silenceTimeout);
                silenceTimeout = null;
            }
        } else {
            // Silence detected
            if (isRecordingSpeech) {
                // If we've been recording for at least 0.5 seconds, set timeout to process
                const recordingDuration = Date.now() - speechStartTime;
                if (recordingDuration > 500 && !silenceTimeout) {
                    // Wait for silence duration before processing
                    if (!silenceTimeout) {
                        silenceTimeout = setTimeout(() => {
                            // End of speech - stop recording and process
                            if (isRecordingSpeech && callMediaRecorder.state === 'recording') {
                                console.log("🔇 Silence detected after speech - stopping recording");
                                try {
                                    callMediaRecorder.stop(); // This will trigger onstop -> processSpeechChunk
                                    callStatusText.textContent = "Transcribing...";
                                    setStatus("Transcribing...");
                                } catch (err) {
                                    console.error("Error stopping MediaRecorder:", err);
                                    isRecordingSpeech = false;
                                    isProcessingChunk = false;
                                }
                            }
                            silenceTimeout = null;
                        }, silenceDuration);
                    }
                }
            }
        }
        
        // Continue checking
        requestAnimationFrame(checkVoiceActivity);
    }
    
    // Note: onstop handler is now set in startVoiceCall() before starting VAD
    // Start VAD loop
    checkVoiceActivity();
}

function stopVoiceCall() {
    // Stop call on server
    if (socket && socket.connected) {
        socket.emit('end_call', { session_id: sessionId });
    }
    
    // Stop PCM processor nodes (new method)
    if (pcmProcessorNode) {
        pcmProcessorNode.disconnect();
        pcmProcessorNode = null;
    }
    if (pcmSourceNode) {
        pcmSourceNode.disconnect();
        pcmSourceNode = null;
    }
    if (pcmAudioContext && pcmAudioContext.state !== 'closed') {
        pcmAudioContext.close();
        pcmAudioContext = null;
    }
    
    // Stop recording if active (legacy MediaRecorder cleanup)
    if (callMediaRecorder && callMediaRecorder.state !== 'inactive') {
        callMediaRecorder.stop();
    }
    
    // Stop stream
    if (callStream) {
        callStream.getTracks().forEach(track => track.stop());
        callStream = null;
    }
    
    // Stop current audio
    if (currentAudioElement) {
        currentAudioElement.pause();
        currentAudioElement = null;
    }
    audioQueueBuffer = [];
    
    // Reset PCM playback state
    pcmAccumulatorBuffer = [];
    pcmAccumulatorSize = 0;
    pcmPlaybackScheduledTime = 0;
    pcmIsFirstChunk = true;
    pcmGainNode = null;
    voiceAgentAudioQueue = [];
    voiceAgentPlaying = false;
    if (voiceAgentAudioContext && voiceAgentAudioContext.state !== 'closed') {
        voiceAgentAudioContext.close();
        voiceAgentAudioContext = null;
    }
    
    // Reset state
    isInCall = false;
    callMediaRecorder = null;
    isProcessingChunk = false;
    
    // Update UI
    callBtn.classList.remove("active");
    callBtn.innerHTML = "📞";
    callBtn.title = "Start Voice Call";
    callStatus.classList.remove("active");
    container.classList.remove("in-call");
    setStatus("Voice call ended");
    
    console.log("[Voice Call] Stopped and cleaned up");
}

// Process complete speech chunk (called when user finishes speaking)
async function processSpeechChunk() {
    if (isProcessingChunk || currentCallChunks.length === 0) {
        return;
    }
    
    isProcessingChunk = true;
    callStatusText.textContent = "Transcribing...";
    
    try {
        // Create blob from complete speech chunk
        console.log(`📊 Processing speech: ${currentCallChunks.length} chunks, total size: ${currentCallChunks.reduce((sum, chunk) => sum + chunk.size, 0)} bytes`);
        const speechBlob = new Blob(currentCallChunks, { type: "audio/webm" });
        
        // Store chunks temporarily (will be reset after processing)
        const chunksToProcess = [...currentCallChunks];
        
        // Reset chunks for next speech (do this before async operations)
        currentCallChunks = [];
        
        // Skip if chunk is too small (lowered threshold for better sensitivity)
        if (speechBlob.size < 2000) { // Less than 2KB is likely too short (was 3KB)
            console.log(`Skipping chunk: too small (${speechBlob.size} bytes)`);
            isProcessingChunk = false;
            callStatusText.textContent = "Voice call active - Speak naturally...";
            return;
        }
        
        // Send to backend for transcription and response
        const formData = new FormData();
        formData.append("audio", speechBlob, "speech_chunk.webm");
        
        console.log(`📤 Sending speech chunk to backend: ${speechBlob.size} bytes`);
        const res = await fetch("/voice-call-chunk", {
            method: "POST",
            body: formData
        });
        
        const data = await res.json();
        
        if (data.error) {
            console.error("Call chunk error:", data.error);
            isProcessingChunk = false;
            callStatusText.textContent = "Voice call active - Speak naturally...";
            return;
        }
        
        // Only process if we have valid transcription
        if (!data.transcription || !data.transcription.trim() || data.transcription.startsWith("[STT error")) {
            console.log("No valid transcription - skipping (might be silence or noise)");
            isProcessingChunk = false;
            callStatusText.textContent = "Voice call active - Speak naturally...";
            setStatus("Voice call active - Speak naturally...");
            // Ensure MediaRecorder is ready for next speech (don't leave it in stopped state)
            if (callMediaRecorder && callMediaRecorder.state === 'inactive') {
                // MediaRecorder will be started again when speech is detected by VAD
                console.log("✅ MediaRecorder ready for next speech");
            }
            return;
        }
        
        // Show user transcription IMMEDIATELY in chat (like ChatGPT/Sesame)
        addMessage(data.transcription, true);
        lastTranscriptionTime = Date.now();
        callStatusText.textContent = "Jarvis is speaking...";
        
        // Get AI response text (use text field, fallback to response for compatibility)
        const aiResponseText = (data.text || data.response || "").trim();
        
        // Show AI text response IMMEDIATELY in chat (before audio plays)
        if (aiResponseText) {
            addMessage(aiResponseText, false);
        }
        
        // Play audio response automatically (non-blocking)
        if (data.audio_url && data.audio_url.trim()) {
            // Stop any existing call audio
            const existingAudio = document.querySelector('audio[data-call-audio]');
            if (existingAudio) {
                existingAudio.pause();
                existingAudio.remove();
            }
            
            // Create and play audio (non-blocking)
            const audio = new Audio(data.audio_url);
            audio.setAttribute('data-call-audio', 'true');
            audio.volume = 0.9;
            audio.crossOrigin = "anonymous";
            
            // Update status when audio starts playing
            audio.addEventListener('play', () => {
                callStatusText.textContent = "Jarvis is speaking...";
            });
            
            audio.addEventListener('ended', () => {
                audio.remove();
                callStatusText.textContent = "Voice call active - Speak naturally...";
            });
            
            audio.addEventListener('error', (err) => {
                console.error("Error playing call audio:", err);
                // Audio failed, but text is already shown, so just update status
                callStatusText.textContent = "Voice call active - Speak naturally...";
            });
            
            // Play audio (don't await - non-blocking)
            audio.play().catch(err => {
                console.error("Error playing call audio:", err);
                callStatusText.textContent = "Voice call active - Speak naturally...";
            });
        } else {
            // No audio, but text is already shown
            callStatusText.textContent = "Voice call active - Speak naturally...";
        }
        
        // Reset processing flag - ready for next speech
        isProcessingChunk = false;
        console.log("✅ Speech chunk processed, ready for next input");
        
        // Ensure MediaRecorder state is clean for next speech (VAD will start it when needed)
        if (callMediaRecorder && callMediaRecorder.state !== 'recording') {
            // MediaRecorder is stopped, VAD will start it again when speech detected
            console.log("✅ MediaRecorder ready for next speech detection");
        }
        
    } catch (err) {
        console.error("Error processing speech chunk:", err);
        isProcessingChunk = false;
        callStatusText.textContent = "Voice call active - Speak naturally...";
    }
}

// Call button event listener
callBtn.addEventListener("click", () => {
    if (isInCall) {
        stopVoiceCall();
    } else {
        startVoiceCall();
    }
});

// Initialize WebSocket connection
function initWebSocket() {
    // Get or create session ID
    sessionId = getSessionId();
    
    // Connect to WebSocket server
    socket = io({
        auth: {
            session_id: sessionId
        }
    });
    
    // Connection events
    socket.on('connect', () => {
        console.log('✅ WebSocket connected');
        setStatus('Connected');
    });
    
    socket.on('connect_error', (error) => {
        console.error('❌ WebSocket connection error:', error);
        setStatus('Failed to connect to server. Make sure app.py is running.');
    });
    
    socket.on('disconnect', () => {
        console.log('⚠️ WebSocket disconnected');
        if (isInCall) {
            setStatus('Connection lost - reconnecting...');
        } else {
            setStatus('Disconnected from server');
        }
    });
    
    socket.on('connected', (data) => {
        sessionId = data.session_id;
        console.log('Session ID:', sessionId);
    });
    
    // Voice call events
    socket.on('call_started', (data) => {
        console.log('Call started:', data);
        // Track if using Voice Agent mode
        voiceAgentMode = (data.mode === 'voice_agent');
        console.log('Voice Agent mode:', voiceAgentMode);
        callStatusText.textContent = voiceAgentMode 
            ? 'Voice Agent active - Speak naturally...' 
            : 'Voice call active - Speak naturally...';
        
        // Show system message in chat with time
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        addMessage(`📞 Voice Call Started at ${timeStr}`, false, { isSystemMessage: true });
    });
    
    socket.on('call_ended', (data) => {
        console.log('Call ended:', data);
        voiceAgentMode = false;
        
        // Show system message in chat with time
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        addMessage(`📞 Voice Call Ended at ${timeStr}`, false, { isSystemMessage: true });
        
        if (isInCall) {
            stopVoiceCall();
        }
    });
    
    // Real-time transcription (from voice call)
    socket.on('transcription', (data) => {
        if (data.is_final && data.text) {
            // Show final transcription in chat with call icon
            addMessage(data.text, true, { isCallMessage: true });
            
            // If agent was speaking and user interrupted, clear buffer
            if (voiceAgentMode && voiceAgentPlaying) {
                console.log('[Voice Agent] User interrupted agent - clearing audio buffer');
                pcmAccumulatorBuffer = [];
                pcmAccumulatorSize = 0;
                pcmIsFirstChunk = true;
            }
        }
    });
    
    // LLM response text (from voice call)
    socket.on('response_text', (data) => {
        if (data.text) {
            // Show AI response text immediately with call icon
            addMessage(data.text, false, { isCallMessage: true });
        }
    });
    
    // Agent status updates (for Voice Agent mode)
    socket.on('agent_status', (data) => {
        if (data.status === 'thinking') {
            callStatusText.textContent = "Jarvis is thinking...";
        } else if (data.status === 'speaking') {
            callStatusText.textContent = "Jarvis is speaking...";
            // Clear accumulated buffer when agent starts speaking (new response)
            if (voiceAgentMode) {
                console.log('[Voice Agent] Agent started speaking - clearing buffer for new response');
                pcmAccumulatorBuffer = [];
                pcmAccumulatorSize = 0;
                pcmIsFirstChunk = true; // Reset for new response
            }
        } else if (data.status === 'listening') {
            callStatusText.textContent = "Voice call active - Speak naturally...";
        }
    });
    
    // Handle agent_speaking event (if emitted separately from agent_status)
    socket.on('agent_speaking', (data) => {
        console.log('[Voice Agent] Agent started speaking (direct event)');
        if (voiceAgentMode) {
            // Clear accumulated buffer to prevent stale audio from previous response
            pcmAccumulatorBuffer = [];
            pcmAccumulatorSize = 0;
            pcmIsFirstChunk = true; // Reset for new response
            callStatusText.textContent = "Jarvis is speaking...";
        }
    });
    
    // Agent finished speaking - flush remaining audio buffer
    socket.on('agent_done', (data) => {
        console.log('[Voice Agent] Agent done speaking');
        // Flush any remaining buffered audio immediately (don't wait for threshold)
        if (pcmAccumulatorBuffer && pcmAccumulatorBuffer.length > 0) {
            console.log('[Voice Agent] Flushing remaining audio buffer:', pcmAccumulatorSize, 'bytes');
            // Force flush immediately to play remaining audio
            flushPCMBuffer();
        }
    });
    
    // Streaming audio chunks (supports both Voice Agent PCM and legacy MP3)
    socket.on('audio_response', (data) => {
        if (data.audio) {
            // Decode base64 audio
            const audioBytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
            playStreamingAudio(audioBytes, voiceAgentMode);
        }
    });
    
    // Error handling
    socket.on('error', (data) => {
        console.error('WebSocket error:', data);
        setStatus('Error: ' + (data.message || 'Unknown error'));
    });
}

// Get or create session ID
function getSessionId() {
    // Try to get from session storage
    let sid = sessionStorage.getItem('session_id');
    if (!sid) {
        sid = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        sessionStorage.setItem('session_id', sid);
    }
    return sid;
}

// Track Voice Agent mode
let voiceAgentMode = false;

// Audio context for PCM playback (Voice Agent mode)
let voiceAgentAudioContext = null;
let voiceAgentAudioQueue = [];
let voiceAgentPlaying = false;

// Play streaming audio chunks
// Supports both Voice Agent PCM (16-bit, 24kHz) and legacy MP3
let currentAudioElement = null;
let audioQueueBuffer = [];

function playStreamingAudio(audioBytes, isVoiceAgentMode = false) {
    if (isVoiceAgentMode) {
        // Voice Agent mode: PCM 16-bit, 24kHz
        playPCMAudio(audioBytes);
    } else {
        // Legacy mode: MP3 from Edge TTS
        playMP3Audio(audioBytes);
    }
}

// Accumulator for smooth audio playback
let pcmAccumulatorBuffer = [];
let pcmAccumulatorSize = 0;
const PCM_MIN_BUFFER_SIZE = 48000; // Buffer 1 second before playing (24kHz * 2 bytes * 1 sec)
let pcmPlaybackScheduledTime = 0;
let pcmIsFirstChunk = true;
let pcmGainNode = null; // For smooth volume control

function playPCMAudio(audioBytes) {
    // Create AudioContext if not exists
    if (!voiceAgentAudioContext) {
        voiceAgentAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 24000
        });
        pcmPlaybackScheduledTime = 0;
        pcmIsFirstChunk = true;
        
        // Create gain node for smooth audio
        pcmGainNode = voiceAgentAudioContext.createGain();
        pcmGainNode.gain.value = 1.0;
        pcmGainNode.connect(voiceAgentAudioContext.destination);
    }
    
    // Resume context if suspended (browser autoplay policy)
    if (voiceAgentAudioContext.state === 'suspended') {
        voiceAgentAudioContext.resume();
    }
    
    try {
        // Accumulate chunks for smoother playback
        pcmAccumulatorBuffer.push(audioBytes);
        pcmAccumulatorSize += audioBytes.length;
        
        // Reduced buffer threshold for faster start and smoother playback
        // First chunk: 0.5 seconds (24000 bytes @ 24kHz 16-bit) - faster start
        // Subsequent chunks: 0.2 seconds (9600 bytes) - smoother streaming
        const bufferThreshold = pcmIsFirstChunk ? 24000 : 9600;
        
        // Only start playback when we have enough buffered
        if (pcmAccumulatorSize >= bufferThreshold) {
            flushPCMBuffer();
            pcmIsFirstChunk = false;
        }
    } catch (err) {
        console.error('[PCM Audio] Error buffering audio:', err);
    }
}

function flushPCMBuffer() {
    if (pcmAccumulatorBuffer.length === 0) return;
    
    // Combine all accumulated chunks into one
    const totalLength = pcmAccumulatorBuffer.reduce((sum, arr) => sum + arr.length, 0);
    const combinedBuffer = new ArrayBuffer(totalLength);
    const combinedView = new Uint8Array(combinedBuffer);
    
    let offset = 0;
    for (const chunk of pcmAccumulatorBuffer) {
        combinedView.set(chunk, offset);
        offset += chunk.length;
    }
    
    // Clear accumulator
    pcmAccumulatorBuffer = [];
    pcmAccumulatorSize = 0;
    
    // Convert to Float32
    const int16Array = new Int16Array(combinedBuffer);
    const float32Array = new Float32Array(int16Array.length);
    
    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
    }
    
    // REMOVED: Fade in/out between chunks - this was causing "cut cut" audio issues
    // The fade was cutting the beginning and end of each chunk, making speech sound choppy
    // Audio chunks from Deepgram are already smooth, no need for additional fading
    
    // Create audio buffer
    const audioBuffer = voiceAgentAudioContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);
    
    // Schedule playback seamlessly
    const source = voiceAgentAudioContext.createBufferSource();
    source.buffer = audioBuffer;
    
    // Connect through gain node for smooth audio
    if (pcmGainNode) {
        source.connect(pcmGainNode);
    } else {
        source.connect(voiceAgentAudioContext.destination);
    }
    
    // Schedule at the right time for gapless playback
    const currentTime = voiceAgentAudioContext.currentTime;
    // Increased overlap to 10ms for better gapless playback (prevents gaps between chunks)
    const startTime = Math.max(currentTime + 0.01, pcmPlaybackScheduledTime - 0.01);
    
    source.start(startTime);
    pcmPlaybackScheduledTime = startTime + audioBuffer.duration;
    
    voiceAgentPlaying = true;
    callStatusText.textContent = "Jarvis is speaking...";
    
    source.onended = () => {
        // Check if more audio is expected
        if (pcmAccumulatorBuffer.length === 0 && voiceAgentAudioQueue.length === 0) {
            // Reduced delay before marking as done (in case more chunks coming)
            setTimeout(() => {
                if (pcmAccumulatorBuffer.length === 0) {
                    voiceAgentPlaying = false;
                    callStatusText.textContent = "Voice Agent active - Speak naturally...";
                }
            }, 300);
        }
    };
}

function playNextPCMChunk() {
    if (voiceAgentAudioQueue.length === 0) {
        voiceAgentPlaying = false;
        callStatusText.textContent = "Voice call active - Speak naturally...";
        return;
    }
    
    voiceAgentPlaying = true;
    callStatusText.textContent = "Jarvis is speaking...";
    
    const audioBuffer = voiceAgentAudioQueue.shift();
    const source = voiceAgentAudioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(voiceAgentAudioContext.destination);
    
    source.onended = () => {
        playNextPCMChunk();
    };
    
    source.start();
}

function playMP3Audio(audioBytes) {
    // Create blob from audio bytes (MP3)
    const blob = new Blob([audioBytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    
    // Stop current audio if playing
    if (currentAudioElement) {
        currentAudioElement.pause();
        currentAudioElement = null;
    }
    
    // Create and play audio element
    const audio = new Audio(url);
    audio.volume = 0.9;
    currentAudioElement = audio;
    
    audio.addEventListener('ended', () => {
        URL.revokeObjectURL(url);
        currentAudioElement = null;
        callStatusText.textContent = "Voice call active - Speak naturally...";
    });
    
    audio.addEventListener('error', (err) => {
        console.error('Error playing streaming audio:', err);
        URL.revokeObjectURL(url);
        currentAudioElement = null;
        callStatusText.textContent = "Voice call active - Speak naturally...";
    });
    
    audio.addEventListener('play', () => {
        callStatusText.textContent = "Jarvis is speaking...";
    });
    
    // Play audio
    audio.play().catch(err => {
        console.error('Error playing audio:', err);
        URL.revokeObjectURL(url);
        currentAudioElement = null;
    });
}

// Load history when page loads
document.addEventListener("DOMContentLoaded", () => {
    loadConversationHistory();
    initWebSocket();
});