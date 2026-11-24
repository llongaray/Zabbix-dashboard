/** Estado mínimo da apresentação: navegação sem recarregar páginas. */
export const $ = selector => document.querySelector(selector);
export const $$ = selector => document.querySelectorAll(selector);

export function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value == null ? '—' : String(value);
}

export function setMessage(selector, message, error = false) {
  const node = $(selector);
  if (!node) return;
  node.textContent = message || '';
  node.classList.toggle('error', !!error);
  node.classList.toggle('ok', !!message && !error);
}

export function showView(name, {push = true} = {}) {
  const link = [...$$('[data-view]')].find(element => element.dataset.view === name);
  if (!link) return;
  if (push && location.pathname !== link.pathname) history.pushState(null, '', link.href);
  $$('.view').forEach(element => {
    element.classList.toggle('active', element.id === 'view-' + name);
  });
  $$('[data-view]').forEach(element => {
    const current = element === link;
    element.classList.toggle('active', current);
    if (current) element.setAttribute('aria-current', 'page');
    else element.removeAttribute('aria-current');
  });
  document.dispatchEvent(new CustomEvent('dashboard:view', {detail: name}));
}

export function onView(name, action) {
  document.addEventListener('dashboard:view', event => {
    if (event.detail === name) action();
  });
}

export function initializeNavigation() {
  const links = [...$$('[data-view]')];
  for (const link of links) {
    link.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      showView(link.dataset.view);
    });
  }
  $$('[data-go]').forEach(button =>
    button.addEventListener('click', () => showView(button.dataset.go)));
  const syncLocation = () => {
    const link = links.find(entry => entry.pathname === location.pathname);
    if (link) showView(link.dataset.view, {push: false});
  };
  window.addEventListener('popstate', syncLocation);
  syncLocation();
}

export function createButton(text, action, className = 'tab') {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = className;
  element.textContent = text;
  element.addEventListener('click', action);
  return element;
}
