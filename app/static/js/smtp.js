import {postJSON, requestJSON} from './api.js';
import {$, setMessage, setText, showView} from './state.js';

function options(select, rows, placeholder, value = '') {
  select.replaceChildren(new Option(placeholder, ''),
    ...rows.map(([label, id]) => new Option(label, id)));
  select.value = value;
}

function checks(selector, rows, selected) {
  const container = $(selector);
  container.replaceChildren(...rows.map(([label, value]) => {
    const wrapper = document.createElement('label');
    wrapper.className = 'alert-check';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = value;
    input.checked = selected.includes(value);
    wrapper.append(input, label);
    return wrapper;
  }));
}

const selected = selector => Array.from($(selector).querySelectorAll('input:checked'), input => input.value);

async function perform(form, status, action) {
  const buttons = Array.from(form.querySelectorAll('button:not(:disabled)'));
  buttons.forEach(button => { button.disabled = true; });
  setMessage(status, '');
  try {
    await action();
  } catch (error) {
    setMessage(status, error.message, true);
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}

export function initializeSmtp() {
  const form = $('#smtp-form');
  const {provider, email, password} = form.elements;
  const senders = $('#smtp-senders');
  const testRecipient = $('#smtp-test-recipient');
  const authorize = $('#smtp-authorize');
  const recipientForm = $('#alert-recipient-form');
  const groupForm = $('#alert-group-form');
  const groupField = name => groupForm.elements.namedItem(name);
  let accounts = [];
  let routing = {groups: [], recipients: [], hosts: []};
  let oauthAvailable = false;

  if (location.hash === '#smtp') {
    showView('settings');
    $('#smtp').scrollIntoView();
  }

  function renderProvider() {
    const gmail = provider.value === 'gmail';
    setText('#smtp-password-label', gmail ? 'Senha de app do Google' : 'Senha SMTP');
    setText('#smtp-help', gmail ? 'Use a senha de app da sua Conta Google.' :
      'Use a senha SMTP se a organização permitir.' +
      (oauthAvailable ? ' Você também pode conectar a conta pela Microsoft.' : ''));
    authorize.hidden = gmail || !oauthAvailable;
  }

  function selectSender() {
    const account = accounts.find(row => row.email.toLowerCase() === senders.value);
    provider.value = account?.provider || 'gmail';
    email.value = account?.email || '';
    password.value = '';
    setText('#smtp-account', account ? 'Credencial salva para ' + account.email : '');
    renderProvider();
  }

  const accountOptions = () => accounts.map(row => [row.email, row.email.toLowerCase()]);
  const recipientOptions = () => routing.recipients.map(address => [address, address.toLowerCase()]);
  const hostOptions = () => routing.hosts.map(host => [host.name || host.host, String(host.hostid)]);

  function renderGroup() {
    const group = routing.groups.find(row => row.id === groupField('id').value);
    groupField('name').value = group?.name || '';
    options(groupField('sender'), accountOptions(), 'Selecione um remetente', group?.sender);
    groupField('scope').value = group?.scope || 'all';
    groupField('enabled').checked = group?.enabled ?? true;
    checks('#alert-group-recipients', recipientOptions(), group?.recipients || []);
    checks('#alert-group-hosts', hostOptions(), group?.hosts || []);
    $('#alert-host-field').hidden = groupField('scope').value !== 'selected';
  }

  async function loadSenders(chosen) {
    const data = await requestJSON('/api/smtp');
    accounts = data.senders;
    oauthAvailable = data.microsoft_oauth;
    options(provider, data.providers.map(item => [item.label, item.id]), 'Selecione o provedor');
    provider.disabled = false;
    options(senders, accountOptions(), 'Novo remetente', chosen ?? accounts[0]?.email.toLowerCase());
    selectSender();
    for (const id of ['#smtp-validate', '#smtp-test', '#smtp-save']) $(id).disabled = false;
  }

  async function loadRouting(chosen = groupField('id').value) {
    routing = await requestJSON('/api/alert-groups');
    const active = routing.groups.filter(group => group.enabled).length;
    const {sent, unconfirmed, collector} = routing.delivery;
    const checked = collector ? new Date(collector.checked_at * 1000).toLocaleString('pt-BR') : null;
    const health = checked ? (collector.ok ? 'Última verificação ' : 'Falha na última verificação ') +
      checked : 'Aguardando o coletor';
    setText('#alert-delivery-summary', active + ' grupo(s) ativo(s) · ' + sent +
      ' enviado(s) · ' + unconfirmed + ' envio(s) sem confirmação nas últimas 24 h · ' + health);
    setText('#alert-recipient-list', routing.recipients.join(', ') || 'Nenhum destinatário cadastrado.');
    options(testRecipient, routing.recipients.map(address => [address, address]),
      'Selecione o destinatário', testRecipient.value);
    options(groupField('id'), routing.groups.map(group => [group.name, group.id]), 'Novo grupo', chosen);
    renderGroup();
  }

  const smtpPayload = () => ({provider: provider.value, email: email.value, password: password.value});
  senders.addEventListener('change', selectSender);
  provider.addEventListener('change', () => {
    password.value = '';
    renderProvider();
  });
  $('#smtp-validate').addEventListener('click', () => {
    if (!form.reportValidity()) return;
    perform(form, '#smtp-status', async () => {
      await postJSON('/api/smtp/validate', smtpPayload());
      setMessage('#smtp-status', 'Autenticação SMTP validada.');
    });
  });
  $('#smtp-test').addEventListener('click', () => {
    if (!form.reportValidity()) return;
    if (!testRecipient.value) {
      setMessage('#smtp-status', 'Cadastre e selecione um destinatário para o teste.', true);
      return;
    }
    perform(form, '#smtp-status', async () => {
      const data = await postJSON('/api/smtp/test', {...smtpPayload(), destination: testRecipient.value});
      setMessage('#smtp-status', 'O provedor aceitou o e-mail de teste para ' + data.email + '.');
    });
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    perform(form, '#smtp-status', async () => {
      const payload = smtpPayload();
      await postJSON('/api/smtp', payload);
      await loadSenders(payload.email.trim().toLowerCase());
      options(groupField('sender'), accountOptions(), 'Selecione um remetente', groupField('sender').value);
      setMessage('#smtp-status', 'Remetente salvo.');
    });
  });
  authorize.addEventListener('click', () => {
    if (!email.reportValidity()) return;
    perform(form, '#smtp-status', async () => {
      const data = await postJSON('/api/smtp/microsoft/authorize', {provider: provider.value, email: email.value});
      location.assign(data.url);
    });
  });

  recipientForm.addEventListener('submit', event => {
    event.preventDefault();
    perform(recipientForm, '#alert-recipient-status', async () => {
      const input = recipientForm.elements.namedItem('email');
      await postJSON('/api/alert-recipients', {email: input.value});
      input.value = '';
      await loadRouting();
      setMessage('#alert-recipient-status', 'Destinatário cadastrado.');
    });
  });
  groupField('id').addEventListener('change', renderGroup);
  groupField('scope').addEventListener('change', () => {
    $('#alert-host-field').hidden = groupField('scope').value !== 'selected';
  });
  groupForm.addEventListener('submit', event => {
    event.preventDefault();
    perform(groupForm, '#alert-group-status', async () => {
      const {group} = await postJSON('/api/alert-groups', {
        id: groupField('id').value, name: groupField('name').value,
        sender: groupField('sender').value, scope: groupField('scope').value,
        enabled: groupField('enabled').checked, recipients: selected('#alert-group-recipients'),
        hosts: selected('#alert-group-hosts'),
      });
      await loadRouting(group.id);
      setMessage('#alert-group-status', 'Grupo salvo.');
    });
  });

  loadSenders().then(() => loadRouting()).catch(error => setMessage('#smtp-status', error.message, true));
  $('[data-view="settings"]').addEventListener('click', () => {
    if (routing.delivery) loadRouting().catch(error => setMessage('#alert-group-status', error.message, true));
  });
}
