const statusElement = document.querySelector("#status");

fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(() => {
    statusElement.textContent = "Backend доступен";
    statusElement.dataset.ok = "true";
  })
  .catch((error) => {
    statusElement.textContent = `Backend недоступен: ${error.message}`;
  });
