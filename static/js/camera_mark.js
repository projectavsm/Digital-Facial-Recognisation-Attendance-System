/**
 * =========================================================
 * camera_mark.js - Attendance Marking Controller
 * =========================================================
 * PURPOSE:
 * 1. Display Pi's hardware camera feed in the browser
 * 2. Trigger 10-second alignment countdown on Pi
 * 3. Poll for recognition results after scan completes
 * 4. Update UI with recognized student information
 * =========================================================
 */

// =========================================================
// DOM ELEMENT REFERENCES
// =========================================================
const startMarkBtn = document.getElementById("startMarkBtn");
const stopMarkBtn = document.getElementById("stopMarkBtn");
const markVideo = document.getElementById("markVideo");
const markStatus = document.getElementById("markStatus");
const recognizedList = document.getElementById("recognizedList");
const countdownOverlay = document.getElementById("countdownOverlay");

// =========================================================
// SESSION STATE TRACKING
// =========================================================
// Tracks students recognized during this browser session
// Prevents duplicate display in the sidebar list
let recognizedIds = new Set();

// Poll interval ID for result checking
let pollInterval = null;

// =========================================================
// EVENT: START ATTENDANCE SCANNING
// =========================================================
/**
 * Triggered when user clicks 'Start Scan' button.
 * 
 * Workflow:
 * 1. Display Pi camera feed in browser
 * 2. Send trigger request to Pi backend
 * 3. Start visual countdown (10s)
 * 4. Poll for recognition results after countdown
 */
startMarkBtn.addEventListener("click", async () => {
    // Update UI: Disable start button, enable stop button
    startMarkBtn.disabled = true;
    stopMarkBtn.disabled = false;
    
    try {
        // Step 1: Connect to Pi's MJPEG stream
        // This displays the live camera feed in the <img> tag
        markVideo.src = "/video_feed";
        markVideo.style.display = "block";
        markStatus.innerText = "Connecting to Pi Camera...";
        
        // Step 2: Request Pi to begin alignment phase
        const res = await fetch("/trigger_attendance");
        
        if (!res.ok) {
            throw new Error("Failed to trigger attendance");
        }
        
        const data = await res.json();
        
        if (data.status === "aligning") {
            // Step 3: Start visual countdown matching Pi's internal timer
            runVisualCountdown(data.seconds);
        } else if (data.status === "busy") {
            markStatus.innerText = "System Busy. Please wait and try again.";
            resetButtons();
        }
        
    } catch (err) {
        console.error("Connection error:", err);
        markStatus.innerText = "Error: Could not reach Pi Server";
        markStatus.classList.add("text-danger");
        resetButtons();
    }
});

// =========================================================
// COUNTDOWN TIMER LOGIC
// =========================================================
/**
 * Displays a visual countdown overlay on the video feed.
 * Matches the Pi's 10-second alignment phase.
 * 
 * @param {number} seconds - Duration of countdown (typically 10)
 */
function runVisualCountdown(seconds) {
    let timeLeft = seconds;
    
    // Show the large countdown overlay
    if (countdownOverlay) {
        countdownOverlay.style.display = "block";
        countdownOverlay.innerText = timeLeft;
    }
    
    // Update every second
    const timer = setInterval(() => {
        timeLeft -= 1;
        
        // Update overlay and status text
        if (countdownOverlay) {
            countdownOverlay.innerText = timeLeft;
        }
        markStatus.innerText = `Aligning face... Scan in ${timeLeft}s`;
        
        if (timeLeft <= 0) {
            clearInterval(timer);
            
            // Hide countdown overlay
            if (countdownOverlay) {
                countdownOverlay.style.display = "none";
            }
            
            // Update status to scanning phase
            markStatus.innerText = "Scanning... Processing AI recognition";
            markStatus.className = "mt-3 fs-5 fw-bold text-warning";
            
            // Start polling for results
            // Pi needs ~1-2 seconds to process, so we poll every 500ms
            startResultPolling();
        }
    }, 1000);
}

// =========================================================
// RESULT POLLING LOGIC
// =========================================================
/**
 * Polls the Pi backend for recognition results.
 * Continues checking until a result is received or timeout occurs.
 */
function startResultPolling() {
    let attempts = 0;
    const maxAttempts = 10; // 5 seconds max (10 * 500ms)
    
    pollInterval = setInterval(async () => {
        attempts++;
        
        try {
            const res = await fetch("/get_scan_result");
            const result = await res.json();
            
            // Check if we have a valid result
            if (result.status) {
                clearInterval(pollInterval);
                handleRecognitionResult(result);
            }
            
            // Timeout check
            if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                markStatus.innerText = "Scan timeout. Please try again.";
                markStatus.className = "mt-3 fs-5 fw-bold text-danger";
                setTimeout(resetButtons, 2000);
            }
            
        } catch (err) {
            console.error("Polling error:", err);
        }
        
    }, 500); // Poll every 500ms
}

function stopStream() {
    markVideo.src = ""; // Clear the MJPEG stream
    // If using WebRTC/Browser Camera (Navigator):
    // stream.getTracks().forEach(track => track.stop()); 
}


// =========================================================
// RESULT HANDLING
// =========================================================
/**
 * Processes the recognition result from the Pi.
 * Updates UI based on success, duplicate, or failure status.
 * 
 * @param {Object} result - Recognition result from backend
 */
function handleRecognitionResult(result) {
    switch (result.status) {
        case "success":
            // Successful recognition
            markStatus.innerText = `✓ ${result.name} recognized (Confidence: ${result.confidence})`;
            markStatus.className = "mt-3 fs-5 fw-bold text-success";
            
            // Add to recognized list if not already present
            addToRecognizedList(result.name, result.student_id, result.confidence);
            
            // Play success sound (optional)
            playNotificationSound("success");
            break;
            
        case "duplicate":
            // Student already marked today
            markStatus.innerText = `⚠ ${result.name} already marked today`;
            markStatus.className = "mt-3 fs-5 fw-bold text-warning";
            
            playNotificationSound("duplicate");
            break;
            
        case "failure":
            // Recognition failed
            markStatus.innerText = `✗ ${result.message}`;
            markStatus.className = "mt-3 fs-5 fw-bold text-danger";
            
            playNotificationSound("error");
            break;
            
        case "error":
            // System error
            markStatus.innerText = `System Error: ${result.message}`;
            markStatus.className = "mt-3 fs-5 fw-bold text-danger";
            break;
    }
    
    // Reset to idle state after 3 seconds
    setTimeout(() => {
        markStatus.innerText = "Ready for next student. Click 'Start Scan' to continue.";
        markStatus.className = "mt-3 fs-5 fw-bold text-secondary";
        resetButtons();
    }, 3000);
}

// =========================================================
// RECOGNIZED LIST MANAGEMENT
// =========================================================
/**
 * Adds a student to the "Recognized This Session" sidebar.
 * Prevents duplicates using the recognizedIds Set.
 * 
 * @param {string} name - Student name
 * @param {string} studentId - Student ID
 * @param {number} confidence - Recognition confidence score
 */
function addToRecognizedList(name, studentId, confidence) {
    // Check if already added during this session
    if (recognizedIds.has(studentId)) {
        return;
    }
    
    recognizedIds.add(studentId);
    
    // Create list item element
    const listItem = document.createElement("li");
    listItem.className = "list-group-item d-flex justify-content-between align-items-center";
    listItem.innerHTML = `
        <div>
            <strong>${name}</strong>
            <br>
            <small class="text-muted">ID: ${studentId}</small>
        </div>
        <span class="badge bg-success rounded-pill">${(confidence * 100).toFixed(0)}%</span>
    `;
    
    // Add to top of list
    recognizedList.insertBefore(listItem, recognizedList.firstChild);
    
    // Animate entrance (optional)
    listItem.style.opacity = "0";
    setTimeout(() => {
        listItem.style.transition = "opacity 0.5s";
        listItem.style.opacity = "1";
    }, 10);
}

// =========================================================
// EVENT: STOP ATTENDANCE SCANNING
// =========================================================
/**
 * Stops the camera feed and resets the UI.
 * Clears any active polling intervals.
 */
stopMarkBtn.addEventListener("click", () => {
    // Stop any active polling
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    
    // Disconnect from camera stream
    markVideo.src = "";
    markVideo.style.display = "none";
    
    // Reset status
    markStatus.innerText = "System Stopped. Refresh page to restart.";
    markStatus.className = "mt-3 fs-5 fw-bold text-secondary";
    
    resetButtons();
    
    // Reload page to ensure clean state
    setTimeout(() => {
        location.reload();
    }, 1000);
});

// =========================================================
// UTILITY FUNCTIONS
// =========================================================

/**
 * Resets button states to default (Start enabled, Stop disabled).
 */
function resetButtons() {
    startMarkBtn.disabled = false;
    stopMarkBtn.disabled = true;
}

/**
 * Plays notification sounds for different events.
 * Requires audio files in /static/sounds/ directory.
 * 
 * @param {string} type - Sound type: "success", "duplicate", "error"
 */
function playNotificationSound(type) {
    // Optional: Implement browser-based sound feedback
    // Example: const audio = new Audio(`/static/sounds/${type}.mp3`);
    // audio.play();
}

// =========================================================
// PAGE LOAD INITIALIZATION
// =========================================================
/**
 * Runs when page loads.
 * Ensures UI is in correct initial state.
 */
document.addEventListener("DOMContentLoaded", () => {
    markStatus.innerText = "System Idle. Click 'Start Scan' to begin.";
    resetButtons();
});