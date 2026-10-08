document.addEventListener("DOMContentLoaded", function () {
  var year = new Date().getFullYear();
  document.querySelectorAll('footer [role="contentinfo"] p').forEach(function (entry) {
    entry.textContent = entry.textContent.replace(/(Copyright\s+)\d{4}\b/, "$1" + year);
  });
});
