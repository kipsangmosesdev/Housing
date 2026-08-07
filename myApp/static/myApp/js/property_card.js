// Property card js
document.addEventListener("DOMContentLoaded", function () {
  const cards = document.querySelectorAll(".property-card");

  const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target); // Animate once only
      }
    });
  }, {
    threshold: 0.2 // Trigger when 20% of the card is visible
  });

  cards.forEach(card => observer.observe(card));
});