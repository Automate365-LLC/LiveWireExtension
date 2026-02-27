chrome.runtime.onMessage.addListener((message) => {
  const box = document.getElementById('transcript-box');
  if (!box) return;

  const entry = document.createElement('div');
  entry.className = 'entry';
  
  const { type, data, timestamp, status } = message;

  if (type === 'TRANSCRIPT_UPDATE') {
    // Styling based on speaker source
    if (data.includes("MIC")) {
      entry.style.borderLeft = "4px solid #007bff";
      entry.style.background = "#e7f3ff";
    } else {
      entry.style.borderLeft = "4px solid #28a745";
      entry.style.background = "#f0fff4";
    }
    entry.innerHTML = `<span class="time">${timestamp}</span> ${data}`;
  } 
  
  else if (type === 'HEALTH_UPDATE') {
    entry.style.borderLeft = "4px solid #ffc107"; 
    entry.style.background = "#fff3cd";
    entry.innerHTML = `<span class="time">${timestamp}</span> Status Alert: ${status}`;
  }

  if (entry.innerHTML !== "") {
    box.appendChild(entry);
    // Auto-scroll to latest entry
    box.scrollTop = box.scrollHeight;
  }
});