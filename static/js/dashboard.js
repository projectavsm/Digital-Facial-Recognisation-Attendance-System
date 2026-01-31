/* dashboard.js - Combined AI Training & Analytics Logic */

document.addEventListener("DOMContentLoaded", () => {
    // UI Element References
    const trainBtn = document.getElementById("trainBtn");
    const trainProgress = document.getElementById("trainProgress");
    const trainMsg = document.getElementById("trainMsg");
    const progressArea = document.getElementById("progressArea"); // Container for the bar

    let pollInterval = null;

    // --- AI TRAINING LOGIC ---

    /**
     * Polls the server for training progress and updates UI.
     */
    async function pollStatus() {
        try {
            const res = await fetch("/train_status");
            const data = await res.json();

            if (trainProgress) {
                trainProgress.style.width = data.progress + "%";
                trainProgress.innerText = data.progress + "%";
            }
            
            if (trainMsg) {
                trainMsg.innerText = data.message || "Processing...";
            }

            // Stop polling when complete or if system says it's not running
            if (data.progress >= 100 && !data.running) {
                clearInterval(pollInterval);
                finishTrainingUI();
            }
            return data;
        } catch (e) {
            console.error("Polling error:", e);
            return null;
        }
    }

    /**
     * Resets UI and reloads page after successful training.
     */
    function finishTrainingUI() {
        if (trainBtn) trainBtn.disabled = false;
        if (trainMsg) {
            trainMsg.innerText = "✓ Training Complete! Refreshing data...";
            trainMsg.classList.replace('text-primary', 'text-success');
        }
        // Wait 2 seconds so user sees the "Complete" message, then refresh
        setTimeout(() => location.reload(), 2000);
    }

    /**
     * Triggers the training process.
     */
    if (trainBtn) {
        trainBtn.addEventListener("click", async () => {
            // UI Feedback: Disable button and show progress area
            trainBtn.disabled = true;
            if (progressArea) progressArea.classList.remove('d-none');
            if (trainMsg) trainMsg.innerText = "Initializing trainer...";

            try {
                // Trigger the training endpoint (using your preferred route)
                const start = await fetch("/train_model", { method: 'POST' });
                
                if (start.ok || start.status === 202) {
                    // Start polling every 1.5 seconds
                    pollInterval = setInterval(pollStatus, 1500);
                } else {
                    throw new Error("Server rejected training request");
                }
            } catch (err) {
                console.error("Training start failed:", err);
                alert("Failed to start training. Check if the camera is currently in use.");
                trainBtn.disabled = false;
            }
        });
    }

    // --- CHART / ANALYTICS LOGIC ---

    let attendanceChart = null;

    /**
     * Fetches statistics and renders/updates the bar chart.
     */
    async function updateChart() {
        const canvas = document.getElementById("attendanceChart");
        if (!canvas) return; // Exit if chart isn't on this page

        try {
            const res = await fetch("/attendance_stats");
            const data = await res.json();
            const ctx = canvas.getContext("2d");

            if (!attendanceChart) {
                // Initialize Chart
                attendanceChart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels: data.dates,
                        datasets: [{
                            label: "Students Present",
                            data: data.counts,
                            backgroundColor: "rgba(59, 130, 246, 0.7)", // Matches theme blue
                            borderColor: "rgba(59, 130, 246, 1)",
                            borderWidth: 1,
                            borderRadius: 5
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false }
                        },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 } }
                        }
                    }
                });
            } else {
                // Update existing chart data
                attendanceChart.data.labels = data.dates;
                attendanceChart.data.datasets[0].data = data.counts;
                attendanceChart.update();
            }
        } catch (e) {
            console.error("Chart update failed:", e);
        }
    }

    // Initial load and periodic refresh (every 10 seconds)
    updateChart();
    setInterval(updateChart, 10000);
});