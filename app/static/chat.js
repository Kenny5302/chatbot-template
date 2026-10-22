(function () {
  var root = document.querySelector('.chat');
  var slug = root.dataset.slug;
  var I18N = JSON.parse(document.getElementById('i18n').textContent); // {order, labels, strings} for this business
  var log = document.getElementById('log');
  var form = document.getElementById('form');
  var input = document.getElementById('input');
  var send = document.getElementById('send');
  var convKey = 'chat-conv-' + slug;
  var langKey = 'chat-lang-' + slug;
  var convId = null;
  try { convId = sessionStorage.getItem(convKey); } catch (e) {}

  // ---- language -------------------------------------------------------
  function supported(code) { return I18N.order.indexOf(code) !== -1; }

  function storedLanguage() {
    try { var v = localStorage.getItem(langKey); return supported(v) ? v : null; } catch (e) { return null; }
  }

  function browserLanguage() {
    var prefs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
    for (var i = 0; i < prefs.length; i++) {
      var code = String(prefs[i] || '').toLowerCase().split('-')[0];
      if (supported(code)) return code;
    }
    return null;
  }

  var current = storedLanguage() || browserLanguage() || root.dataset.defaultLang;

  function setText(id, value) { var el = document.getElementById(id); if (el) el.textContent = value; }

  function applyLanguage(code, remember) {
    current = code;
    var S = I18N.strings[code];
    document.documentElement.lang = code;
    document.title = S.chat_with;
    setText('subtitle', S.subtitle);
    setText('call', S.call);
    setText('greeting', S.greeting);
    setText('send', S.send);
    input.placeholder = S.placeholder;
    input.setAttribute('aria-label', S.message_label);
    var closeBtn = document.getElementById('close');
    if (closeBtn) closeBtn.setAttribute('aria-label', S.close);
    var group = document.getElementById('langs');
    if (group) {
      group.setAttribute('aria-label', S.language_label);
      Array.prototype.forEach.call(group.querySelectorAll('button[data-lang]'), function (b) {
        b.setAttribute('aria-pressed', b.dataset.lang === code ? 'true' : 'false');
      });
    }
    if (remember) { try { localStorage.setItem(langKey, code); } catch (e) {} }
  }

  var group = document.getElementById('langs');
  if (group) group.addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-lang]');
    if (btn && btn.dataset.lang !== current) applyLanguage(btn.dataset.lang, true);
  });

  applyLanguage(current, false);

  // ---- chat -----------------------------------------------------------
  function add(cls, text) {
    var div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text; // textContent, never innerHTML: customer and model text is untrusted
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  var closeBtn = document.getElementById('close');
  if (closeBtn) closeBtn.addEventListener('click', function () {
    parent.postMessage({ type: 'chat-widget-close' }, '*');
  });

  function grow() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }
  input.addEventListener('input', grow);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  function errorFor(status) {
    var S = I18N.strings[current];
    if (status === 429) return S.error_rate_limit;
    if (status === 422) return S.error_invalid;
    return S.error_generic;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    add('user', text);
    input.value = '';
    grow();
    send.disabled = true;
    var typing = add('bot typing', '...');

    fetch('/api/' + slug + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, conversation_id: convId, language: current })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; }); })
      .then(function (res) {
        typing.remove();
        if (res.ok) {
          convId = res.data.conversation_id;
          try { sessionStorage.setItem(convKey, convId); } catch (e) {}
          add('bot', res.data.reply);
        } else {
          add('error', errorFor(res.status));
        }
      })
      .catch(function () {
        typing.remove();
        add('error', I18N.strings[current].error_network);
      })
      .finally(function () { send.disabled = false; input.focus(); });
  });
})();
