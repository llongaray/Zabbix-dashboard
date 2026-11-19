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

export function showView(name) {
  $$('.view').forEach(element => {
    element.classList.toggle('active', element.id === 'view-' + name);
  });
  $$('[data-view]').forEach(element => {
    element.classList.toggle('active', element.dataset.view === name);
  });
}

export function initializeNavigation() {
  $$('[data-view]').forEach(button =>
    button.addEventListener('click', () => showView(button.dataset.view)));
  $$('[data-go]').forEach(button =>
    button.addEventListener('click', () => showView(button.dataset.go)));
}

export function createButton(text, action, className = 'tab') {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = className;
  element.textContent = text;
  element.addEventListener('click', action);
  return element;
}
