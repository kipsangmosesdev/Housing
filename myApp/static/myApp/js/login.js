 document.addEventListener("DOMContentLoaded", function() {
    const togglePassword = document.querySelector('#togglePassword');
    const password = document.querySelector('#password');
    togglePassword.addEventListener('click', function() {
      const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
      password.setAttribute('type', type);
      this.innerHTML = type === 'password'
        ? '<i class="fas fa-eye"></i>'
        : '<i class="fas fa-eye-slash"></i>';
    });

    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
      form.addEventListener('submit', function(event) {
        if (!form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
        } else {
          const loginButton = document.querySelector('#loginButton');
          const loginText = document.querySelector('#loginText');
          const loginSpinner = document.querySelector('#loginSpinner');
          loginButton.disabled = true;
          loginText.textContent = 'Granting Access...';
          loginSpinner.classList.remove('d-none');
        }
        form.classList.add('was-validated');
      }, false);
    });
  });