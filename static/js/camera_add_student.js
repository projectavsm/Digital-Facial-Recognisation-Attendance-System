/**
 * =========================================================
 * camera_add_student.js - Student Enrollment Controller
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
const saveInfoBtn = document.getElementById("saveInfoBtn");
const startCaptureBtn = document.getElementById("startCaptureBtn");
const addStudentBtn = document.getElementById("addStudentBtn");
const videoFeed = document.getElementById("video");
const cameraPlaceholder = document.getElementById("cameraPlaceholder");
const captureStatus = document.getElementById("captureStatus");
const progressBar = document.getElementById("progressBar");

// =========================================================
// STATE TRACKING
// =========================================================
let student_id = null;

// =========================================================
// STEP 1: SAVE STUDENT INFORMATION
// =========================================================
studentForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    // UI Loading State
    saveInfoBtn.disabled = true;
    saveInfoBtn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...`;
    
    const formData = new FormData(studentForm);
    
    try {
        const res = await fetch("/add_student", {
            method: "POST",
            body: formData
        });
        
        if (!res.ok) throw new Error("Server communication error.");
        
        const data = await res.json();
        
        if (data.status === "success") {
            student_id = data.student_id;
            
            // Success UI Feedback
            captureStatus.innerText = `✓ Student saved (ID: ${student_id}). Ready for capture.`;
            captureStatus.className = "fw-bold text-success mb-2 p-2 border border-success rounded bg-light";
            
            // Enable Next Step
            startCaptureBtn.disabled = false;
            
            // Style Update for Step 1 Button
            saveInfoBtn.innerText = "✓ Information Saved";
            saveInfoBtn.classList.replace("btn-primary", "btn-success");
            
            // Lock inputs to prevent accidental changes after saving
            const inputs = studentForm.querySelectorAll("input");
            inputs.forEach(input => input.readOnly = true);

        } else {
            throw new Error(data.message || "Unknown error");
        }
        
    } catch (err) {
        console.error("Save error:", err);
        captureStatus.innerText = "❌ Error: " + err.message;
        captureStatus.className = "fw-bold text-danger mb-2";
        saveInfoBtn.disabled = false;
        saveInfoBtn.innerText = "1. Save Information";
        alert("Failed to save: " + err.message);
    }
});

// =========================================================
// STEP 2: TRIGGER PI CAMERA CAPTURE
// =========================================================
startCaptureBtn.addEventListener("click", async () => {
    if (!student_id) return;

    startCaptureBtn.disabled = true;
    captureStatus.innerText = "Connecting to Pi Camera...";
    captureStatus.className = "fw-bold text-info mb-2";
    
    try {
        // Show Video, Hide Placeholder
        cameraPlaceholder.style.display = "none";
        videoFeed.src = "/video_feed";
        videoFeed.style.display = "block";
        
        const res = await fetch(`/trigger_capture?student_id=${student_id}`);
        if (!res.ok) throw new Error("Could not reach Pi Camera.");
        
        const data = await res.json();
        
        if (data.status === "capturing") {
            handleEnrollmentUI();
        } else {
            throw new Error(data.message || "Capture initialization failed.");
        }
        
    } catch (err) {
        console.error("Capture trigger failed:", err);
        captureStatus.innerText = "❌ Camera Error: " + err.message;
        captureStatus.className = "fw-bold text-danger mb-2";
        startCaptureBtn.disabled = false;
        
        // Revert UI to placeholder if camera fails
        videoFeed.style.display = "none";
        cameraPlaceholder.style.display = "flex";
    }
});

// =========================================================
// STEP 3: HANDLE UI FEEDBACK (TIMERS)
// =========================================================
function handleEnrollmentUI() {
    let timeLeft = 10;
    
    // Phase 1: Alignment (0-10s)
    const alignTimer = setInterval(() => {
        timeLeft -= 1;
        captureStatus.innerText = `⏱ Aligning... Stay centered! Scan starts in ${timeLeft}s`;
        captureStatus.className = "fw-bold text-warning mb-2";
        
        // Progress: 0 to 50%
        progressBar.style.width = `${((10 - timeLeft) / 10) * 50}%`;
        
        if (timeLeft <= 0) {
            clearInterval(alignTimer);
            startCapturePhase();
        }
    }, 1000);
}

function startCapturePhase() {
    captureStatus.innerText = "📸 Capturing Images... Rotate your head slowly!";
    captureStatus.className = "fw-bold text-primary mb-2";
    
    let captureProgress = 0;
    const updateInterval = 250; 
    
    const captureInterval = setInterval(() => {
        captureProgress += 10; 
        
        // Progress: 50 to 100%
        progressBar.style.width = `${50 + (captureProgress / 2)}%`;
        
        if (captureProgress >= 100) {
            clearInterval(captureInterval);
            finishEnrollment();
        }
    }, updateInterval);
}

// =========================================================
// STEP 4: FINALIZE
// =========================================================
function finishEnrollment() {
    captureStatus.innerText = "✓ Capture Complete! 50 images stored.";
    captureStatus.className = "fw-bold text-success mb-2 p-2 bg-light border border-success rounded";
    
    progressBar.style.width = "100%";
    progressBar.classList.remove("progress-bar-animated");
    
    // Enable Final Button
    addStudentBtn.disabled = false;
    addStudentBtn.classList.add("pulse-animation");
}

addStudentBtn.addEventListener("click", () => {
    const message = `Student ${student_id} Enrolled.\n\n` +
                    `NOTICE: You must run manual_fix.py via SSH to retrain the AI.\n\n` +
                    `Return to dashboard?`;
    
    if (confirm(message)) {
        window.location.href = "/";
    }
});

// Initial Setup
document.addEventListener("DOMContentLoaded", () => {
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
    progressBar.style.width = "0%";
});

// Pulse Animation Styling (if not in CSS file)
if (!document.querySelector('#pulse-style')) {
    const style = document.createElement('style');
    style.id = 'pulse-style';
    style.textContent = `
        @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.8; transform: scale(1.02); } 100% { opacity: 1; transform: scale(1); } }
        .pulse-animation { animation: pulse 1.5s infinite; box-shadow: 0 0 15px rgba(25, 135, 84, 0.5); }
    `;
    document.head.appendChild(style);
}