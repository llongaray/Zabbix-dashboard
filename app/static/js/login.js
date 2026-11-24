const toggle = document.querySelector('#toggle');
const password = document.querySelector('#password');
toggle.addEventListener('click', () => {
  const show = password.type === 'password';
  password.type = show ? 'text' : 'password';
  toggle.textContent = show ? 'Ocultar senha' : 'Mostrar senha';
});
