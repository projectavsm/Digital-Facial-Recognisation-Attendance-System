/**
 * =========================================================
 * camera_add_student.js - Student Enrollment Controller (Fixed)
 * =========================================================
 * PURPOSE:
 * 1. Submit student information to database
 * 2. Trigger Pi camera capture sequence with 10s alignment
 * 3. Display live Pi feed during capture
 * 4. Provide visual progress feedback to user
 * =========================================================
 */

// =========================================================
// DOM ELEMENT REFERENCES
// =========================================================
const studentForm = document.getElementById("studentForm");
const startCaptureBtn = document.getElementById("startCaptureBtn");
const addStudentBtn = document.getElementById("addStudentBtn");
const videoFeed = document.getElementById("video");
const captureStatus = document.getElementById("captureStatus");
const progressBar = document.getElementById("progressBar");

// =========================================================
// STATE TRACKING
// =========================================================
// Stores the student_id returned from the database
// Needed to tell the Pi which folder to save images to
let student_id = null;

// =========================================================
// STEP 1: SAVE STUDENT INFORMATION TO DATABASE
// =========================================================
/**
 * Form submission handler.
 * Sends student data to backend and receives student_id.
 * 
 * Workflow:
 * 1. Validate form data
 * 2. Send POST request to /add_student
 * 3. Store returned student_id
 * 4. Enable capture button
 */
studentForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    // Disable submit to prevent double-submission
    const submitBtn = studentForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.innerText = "Saving...";
    
    // Gather form data
    const formData = new FormData(studentForm);
    
    try {
        // Send to backend
        const res = await fetch("/add_student", {
            method: "POST",
            body: formData
        });
        
        if (!res.ok) {
            throw new Error("Failed to save student information");
        }
        
        const data = await res.json();
        
        if (data.status === "success") {
            // Store the student_id for later use
            student_id = data.student_id;
            
            // Update UI to show success
            captureStatus.innerText = `✓ Student saved (ID: ${student_id}). Ready for capture.`;
            captureStatus.className = "fw-bold text-success mb-1";
            
            // Enable the capture button
            startCaptureBtn.disabled = false;
            
            // Update submit button
            submitBtn.innerText = "✓ Saved";
            submitBtn.classList.replace("btn-primary", "btn-success");
            
            alert(`Student information saved successfully!\n\nID: ${student_id}\n\nNow click 'Start Pi-Capture' to take training photos.`);
            
        } else {
            throw new Error(data.message || "Unknown error");
        }
        
    } catch (err) {
        console.error("Save error:", err);
        alert("Failed to save student information: " + err.message);
        
        // Reset button
        submitBtn.disabled = false;
        submitBtn.innerText = "1. Save Information";
        
        captureStatus.innerText = "Error: " + err.message;
        captureStatus.className = "fw-bold text-danger mb-1";
    }
});

// =========================================================
// STEP 2: TRIGGER PI CAMERA CAPTURE SEQUENCE
// =========================================================
/**
 * Initiates the image capture process on the Pi.
 * 
 * Workflow:
 * 1. Display Pi's live camera feed
 * 2. Send capture trigger to Pi with student_id
 * 3. Start UI countdown and progress bar
 * 4. Monitor capture completion
 */
startCaptureBtn.addEventListener("click", async () => {
    if (!student_id) {
        alert("Error: No student ID found. Please save information first.");
        return;
    }
    
    // Disable button to prevent multiple triggers
    startCaptureBtn.disabled = true;
    
    // Update status
    captureStatus.innerText = "Connecting to Pi Camera...";
    captureStatus.className = "fw-bold text-info mb-1";
    
    try {
        // Step 1: Display the Pi's MJPEG stream
        // This allows the user to see themselves and position correctly
        videoFeed.src = "/video_feed";
        videoFeed.style.display = "block";
        
        // Step 2: Trigger the capture sequence on the Pi
        const res = await fetch(`/trigger_capture?student_id=${student_id}`);
        
        if (!res.ok) {
            throw new Error("Failed to trigger capture");
        }
        
        const data = await res.json();
        
        if (data.status === "capturing") {
            // Step 3: Start UI feedback sequence
            handleEnrollmentUI();
        } else {
            throw new Error(data.message || "Unknown capture error");
        }
        
    } catch (err) {
        console.error("Capture trigger failed:", err);
        
        captureStatus.innerText = "Error: Could not communicate with Pi";
        captureStatus.className = "fw-bold text-danger mb-1";
        
        startCaptureBtn.disabled = false;
        
        alert("Failed to start capture: " + err.message);
    }
});

// =========================================================
// STEP 3: HANDLE UI FEEDBACK DURING CAPTURE
// =========================================================
/**
 * Manages the visual feedback during the enrollment process.
 * 
 * Phase 1 (0-10s): Alignment countdown
 * Phase 2 (10-12.5s): Image capture with progress bar
 */
function handleEnrollmentUI() {
    let timeLeft = 10;
    
    // =====================================================
    // PHASE 1: ALIGNMENT COUNTDOWN (10 seconds)
    // =====================================================
    const alignTimer = setInterval(() => {
        timeLeft -= 1;
        
        // Update status text
        captureStatus.innerText = `⏱ Aligning... Stay centered! Scan starts in ${timeLeft}s`;
        captureStatus.className = "fw-bold text-warning mb-1";
        
        // Progress bar: 0% to 50% during alignment
        const alignmentProgress = ((10 - timeLeft) / 10) * 50;
        progressBar.style.width = `${alignmentProgress}%`;
        
        if (timeLeft <= 0) {
            clearInterval(alignTimer);
            startCapturePhase();
        }
    }, 1000);
}

/**
 * Phase 2: Actual image capture with visual feedback.
 * Pi captures 50 images over ~2.5 seconds (50 frames * 0.05s delay).
 */
function startCapturePhase() {
    captureStatus.innerText = "📸 Capturing 50 images... Move your head slightly!";
    captureStatus.className = "fw-bold text-primary mb-1";
    
    let captureProgress = 0;
    const totalCaptureDuration = 2500; // 2.5 seconds (matches Pi's actual timing)
    const updateInterval = 250; // Update every 250ms (10 updates total)
    
    const captureInterval = setInterval(() => {
        captureProgress += 10; // Increment by 10% each update
        
        // Progress bar: 50% to 100% during capture
        const totalProgress = 50 + (captureProgress / 2);
        progressBar.style.width = `${totalProgress}%`;
        
        if (captureProgress >= 100) {
            clearInterval(captureInterval);
            finishEnrollment();
        }
    }, updateInterval);
}

// =========================================================
// STEP 4: FINALIZE ENROLLMENT
// =========================================================
/**
 * Called after capture completes.
 * Updates UI and enables the finish button.
 */
function finishEnrollment() {
    // Update status to success
    captureStatus.innerText = "✓ Success! 50 images saved to Pi local storage.";
    captureStatus.className = "fw-bold text-success mb-1";
    
    // Ensure progress bar is at 100%
    progressBar.style.width = "100%";
    progressBar.classList.remove("progress-bar-animated");
    
    // Enable finish button
    addStudentBtn.disabled = false;
    addStudentBtn.classList.add("pulse-animation");
    
    // Show completion message
    setTimeout(() => {
        alert("Enrollment Complete!\n\n50 training images captured successfully.\n\nIMPORTANT: You must run 'manual_fix.py' to retrain the model before this student can be recognized.");
    }, 500);
}

// =========================================================
// FINISH BUTTON HANDLER
// =========================================================
/**
 * Redirects to dashboard after enrollment completion.
 * Reminds user about model retraining requirement.
 */
addStudentBtn.addEventListener("click", () => {
    const message = `Enrollment complete for Student ID: ${student_id}\n\n` +
                   `NEXT STEPS:\n` +
                   `1. SSH into the Pi\n` +
                   `2. Run: python3 manual_fix.py\n` +
                   `3. Wait for model retraining to complete\n` +
                   `4. This student will then be recognizable\n\n` +
                   `Return to dashboard?`;
    
    if (confirm(message)) {
        window.location.href = "/";
    }
});

// =========================================================
// PAGE LOAD INITIALIZATION
// =========================================================
/**
 * Ensures UI is in correct initial state when page loads.
 */
document.addEventListener("DOMContentLoaded", () => {
    // Ensure capture button is disabled until student info is saved
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
    
    // Set initial status
    captureStatus.innerText = "Status: Complete the form above to begin";
    captureStatus.className = "fw-bold text-muted mb-1";
    
    // Reset progress bar
    progressBar.style.width = "0%";
});

// =========================================================
// UTILITY: ADD PULSE ANIMATION CSS DYNAMICALLY
// =========================================================
/**
 * Adds a subtle pulse animation to draw attention to the finish button.
 */
if (!document.querySelector('#pulse-animation-style')) {
    const style = document.createElement('style');
    style.id = 'pulse-animation-style';
    style.textContent = `
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        .pulse-animation {
            animation: pulse 1.5s ease-in-out infinite;
        }
    `;
    document.head.appendChild(style);
}