document.addEventListener("DOMContentLoaded", async () => {
  const counter = document.getElementById("count_result");
  if (!counter) {
    return;
  }
  counter.textContent = "0";
  counter.setAttribute("data-count", "0");

  try {
    const response = await fetch("/api/clusters", { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const clusters = await response.json();
    const count = Array.isArray(clusters) ? clusters.length : 0;
    counter.textContent = String(count);
    counter.setAttribute("data-count", String(count));
  } catch (_err) {
    console.error("Unable to load cluster count from API.");
  }
});
