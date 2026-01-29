/* admin.js - Combined Admin Panel Logic */

let pollInterval;

// --- AI TRAINING LOGIC ---

function startTraining() {
    const btn = document.getElementById('trainBtn');
    const area = document.getElementById('progressArea');
    
    if (btn) btn.disabled = true;
    if (area) area.classList.remove('d-none');

    fetch('/admin/train_trigger', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            pollInterval = setInterval(checkStatus, 1000);
        })
        .catch(err => {
            console.error("Training trigger failed:", err);
            if (btn) btn.disabled = false;
        });
}

function checkStatus() {
    fetch('/train_status')
        .then(res => res.json())
        .then(status => {
            const bar = document.getElementById('progressBar');
            const msg = document.getElementById('trainMessage');

            if (bar) {
                bar.style.width = status.progress + '%';
                bar.innerText = status.progress + '%';
            }
            if (msg) msg.innerText = status.message;

            if (!status.running && status.progress === 100) {
                clearInterval(pollInterval);
                if (msg) {
                    msg.innerText = "Training Complete! Refreshing...";
                    msg.classList.replace('text-primary', 'text-success');
                }
                setTimeout(() => location.reload(), 2000);
            }
        });
}

// --- DELETE CONFIRMATION LOGIC ---

/**
 * Intercepts the delete form submission to ask for confirmation.
 * @param {string} studentName - The name of the student to show in the alert.
 */
function confirmDelete(studentName) {
    const message = `⚠️ CAUTION: Are you sure you want to delete ${studentName}?\n\nThis will permanently remove their database record and all 50 facial images from the dataset folder.`;
    return confirm(message);
}