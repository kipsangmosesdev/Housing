
    // Enable tooltips
    document.addEventListener('DOMContentLoaded', function() {
      var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
      var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
      });
      
      // Smooth scroll for anchor links
      document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
          e.preventDefault();
          document.querySelector(this.getAttribute('href')).scrollIntoView({
            behavior: 'smooth'
          });
        });
      });
    });

// Navbar scroll behavior
document.addEventListener("scroll", function() {
  const navbar = document.querySelector(".navbar");
  if (window.scrollY > 30) {
    navbar.classList.add("scrolled");
  } else {
    navbar.classList.remove("scrolled");
  }
});

// Auto-dismiss alerts
document.addEventListener("DOMContentLoaded", function () {
    const alerts = document.querySelectorAll('.auto-dismiss');
    alerts.forEach(alert => {
      setTimeout(() => {
        let bsAlert = new bootstrap.Alert(alert);
        bsAlert.close();   // Smoothly closes the alert
      }, 4000); // 4 seconds delay
    });
  });