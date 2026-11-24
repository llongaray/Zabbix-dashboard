(() => {
  const root = document.documentElement;
  const preference = window.matchMedia('(prefers-color-scheme: dark)');
  const key = 'zabbix-dashboard-theme';
  let saved;
  try { saved = localStorage.getItem(key); } catch {}

  function setTheme(dark) {
    root.dataset.theme = dark ? 'dark' : 'light';
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.setAttribute('aria-pressed', String(dark));
      button.textContent = dark ? 'Tema claro' : 'Tema escuro';
    }
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0e0a1c' : '#f7f7fb');
  }

  const preferred = () => saved === 'dark' || (saved !== 'light' && preference.matches);
  setTheme(preferred());
  document.addEventListener('DOMContentLoaded', () => setTheme(preferred()));
  document.addEventListener('click', event => {
    if (!event.target.closest('#theme-toggle')) return;
    const dark = root.dataset.theme !== 'dark';
    saved = dark ? 'dark' : 'light';
    try { localStorage.setItem(key, saved); } catch {}
    setTheme(dark);
  });
})();
