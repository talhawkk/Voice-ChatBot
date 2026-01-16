let mediaRecorder;
let chunks = [];
let isRecording = false;
let isPaused = false;
let currentStream = null;
let recordingStartTime = null;
let recordedBlob = null;

const recordBtn = document.getElementById("record-btn");
const sendBtn = document.getElementById("send-btn");
const messageInput = document.getElementById("message-input");
const statusEl = document.getElementById("status");
const chatContainer = document.getElementById("chat-container");
const emptyState = document.getElementById("empty-state");

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

function addMessage(text, isUser) {
    // Hide empty state if it exists
    if (emptyState) {
        emptyState.style.display = "none";
    }
    
    // Create message element
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user" : "assistant"}`;
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text;
    
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
    audio.preload = "metadata";
    // Add CORS support for S3 URLs
    if (audioUrl.startsWith("http://") || audioUrl.startsWith("https://")) {
        audio.crossOrigin = "anonymous";
    }
    
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
        const mins = Math.floor(audio.duration / 60);
        const secs = Math.floor(audio.duration % 60);
        duration.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    });
    
    // Play/pause functionality
    let isPlaying = false;
    playBtn.addEventListener("click", () => {
        if (isPlaying) {
            audio.pause();
            playBtn.innerHTML = "▶";
            bubble.classList.remove("playing");
            isPlaying = false;
        } else {
            audio.play();
            playBtn.innerHTML = "⏸";
            bubble.classList.add("playing");
            isPlaying = true;
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
        setStatus("Mic permission denied or unavailable");
        addMessage("Error: Microphone permission denied", false);
        console.error(err);
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
        
        // Generate and show AI response
        if (data.transcription) {
            await generateAIResponse(data.transcription, data.message_id);
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

async function generateAIResponse(transcription, user_message_id) {
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
                message_id: user_message_id
            }),
        });
        
        const data = await res.json();
        hideTypingIndicator();
        
        if (data.error || res.status !== 200) {
            setStatus("Error: " + (data.error || "Failed to get response"));
            addMessage(data.error || "Error: Failed to get AI response", false);
            return;
        }
        
        // Check if it's an error message in the text
        if (data.text && (data.text.startsWith("Sorry, I encountered an error") || data.text.startsWith("Sorry, I've reached"))) {
            addMessage(data.text, false);
            setStatus("API limit reached");
            return;
        }
        
        // Add AI voice response (with text as transcription)
        if (data.audio_url && data.audio_url.trim() !== "") {
            addVoiceMessage(data.audio_url, false, data.message_id, data.text || "");
        } else if (data.text) {
            // Fallback: if no audio, just show text
            addMessage(data.text, false);
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

// Load history when page loads
document.addEventListener("DOMContentLoaded", () => {
    loadConversationHistory();
});