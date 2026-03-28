/**
 * camera_add_student.js - Final Version
 */

const studentForm = document.getElementById("studentForm");
const saveInfoBtn = document.getElementById("saveInfoBtn");
const startCaptureBtn = document.getElementById("startCaptureBtn");
const addStudentBtn = document.getElementById("addStudentBtn");
const videoFeed = document.getElementById("video");
const cameraPlaceholder = document.getElementById("cameraPlaceholder");
const captureStatus = document.getElementById("captureStatus");
const progressBar = document.getElementById("progressBar");

let student_id = null;

// =========================================================
// STEP 1: SAVE INFORMATION (Triggered by button click)
// =========================================================
saveInfoBtn.addEventListener("click", async () => {
    // Basic validation check
    const requiredInputs = studentForm.querySelectorAll("[required]");
    let valid = true;
    requiredInputs.forEach(input => { if(!input.value) valid = false; });
    
    if(!valid) {
        alert("Please fill in all required fields (*)");
        return;
    }

    // UI Loading State
    saveInfoBtn.disabled = true;
    saveInfoBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;
    
    const formData = new FormData(studentForm);
    
    try {
        const res = await fetch("/enrollment", {
            method: "POST",
            body: formData
        });
        
        const data = await res.json();
        
        if (data.status === "success") {
            student_id = data.student_id;
            captureStatus.innerText = `✓ Student saved (ID: ${student_id}). Ready for capture.`;
            captureStatus.className = "fw-bold text-success mb-2 p-2 border border-success rounded bg-light";
            
            startCaptureBtn.disabled = false;
            saveInfoBtn.innerText = "✓ Information Saved";
            saveInfoBtn.classList.replace("btn-primary", "btn-success");
            
            // Lock inputs
            studentForm.querySelectorAll("input").forEach(i => i.readOnly = true);
        } else {
            throw new Error(data.message || "Unknown error");
        }
    } catch (err) {
        console.error("Save error:", err);
        saveInfoBtn.disabled = false;
        saveInfoBtn.innerText = "Save Information";
        alert("Error: " + err.message);
    }
});

// =========================================================
// STEP 2: CAPTURE
// =========================================================
// =========================================================
// STEP 2: CAPTURE
// =========================================================
startCaptureBtn.addEventListener("click", async () => {
    if (!student_id) return;
    
    const placeholder = document.getElementById('cameraPlaceholder');
    const videoSection = document.getElementById('videoSection');
    const videoImg = document.getElementById('video');

    // 1. FORCE THE SWAP
    if (placeholder) {
        placeholder.classList.add('d-none'); // Uses your CSS !important rule
        placeholder.style.display = 'none';  // Double insurance
    }
    
    if (videoSection) {
        videoSection.classList.remove('d-none');
        videoSection.style.display = 'block';
    }

    startCaptureBtn.disabled = true;
    captureStatus.innerText = "Connecting to Pi Camera...";
    
    try {
        // 2. Start the Video Feed
        if (videoImg) {
            videoImg.src = "/video_feed?t=" + new Date().getTime();
        }
        
        const res = await fetch(`/trigger_capture?student_id=${student_id}`);
        const data = await res.json();
        
        if (data.status === "capturing") {
            handleEnrollmentUI();
        }
    } catch (err) {
        alert("Camera Error: " + err.message);
        startCaptureBtn.disabled = false;
        // Re-show placeholder on error
        placeholder.classList.remove('d-none');
    }
});
function handleEnrollmentUI() {
    let timeLeft = 10;
    const alignTimer = setInterval(() => {
        timeLeft -= 1;
        captureStatus.innerText = `⏱ Aligning... Scan starts in ${timeLeft}s`;
        progressBar.style.width = `${((10 - timeLeft) / 10) * 50}%`;
        if (timeLeft <= 0) {
            clearInterval(alignTimer);
            startCapturePhase();
        }
    }, 1000);
}

async function startCapturePhase() {
    captureStatus.innerText = "📸 Capturing 50 Images... Rotate head slowly!";
    let count = 0;
    const total = 50;

    const captureInterval = setInterval(async () => {
        count++;
        
        // 1. Draw current video frame to a hidden canvas
        const canvas = document.createElement("canvas");
        canvas.width = videoFeed.videoWidth || 640;
        canvas.height = videoFeed.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(videoFeed, 0, 0);

        // 2. Convert to Blob and upload
        canvas.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append("student_id", student_id);
            formData.append("images[]", blob, `cap_${count}.jpg`);

            await fetch("/upload_face", { method: "POST", body: formData });
        }, "image/jpeg");

        // 3. Update Progress
        let progressPercent = 50 + ((count / total) * 50);
        progressBar.style.width = `${progressPercent}%`;

        if (count >= total) {
            clearInterval(captureInterval);
            finishEnrollment();
        }
    }, 200); // Takes 5 photos per second
}

function finishEnrollment() {
    captureStatus.innerText = "✓ Capture Complete!";
    progressBar.style.width = "100%";
    addStudentBtn.disabled = false;
}

addStudentBtn.addEventListener("click", () => {
    if (confirm("Student Enrolled. Return to dashboard?")) {
        window.location.href = "/";
    }
});