document.addEventListener("DOMContentLoaded", async () => {
  const counter = document.getElementById("count_result");
  if (!counter) {
    return;
  }
  counter.textContent = "0";
  counter.setAttribute("data-count", "0");

  const endpoints = ["/api/clusters", "http://localhost:8000/api/clusters"];
  for (const url of endpoints) {
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        continue;
      }
      const clusters = await response.json();
      const count = Array.isArray(clusters) ? clusters.length : 0;
      counter.textContent = count;
      counter.setAttribute("data-count", count);
      return;
    } catch (err) {
      continue;
    }
  }
  console.error("Unable to load cluster count from API.");
});
