(function () {
  var root = document.querySelector('.chat');
  var slug = root.dataset.slug;
  var phone = root.dataset.phone;
  var log = document.getElementById('log');
  var form = document.getElementById('form');
  var input = document.getElementById('input');
  var send = document.getElementById('send');
  var storeKey = 'chat-conv-' + slug;
  var convId = null;
  try { convId = sessionStorage.getItem(storeKey); } catch (e) {}

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
      body: JSON.stringify({ message: text, conversation_id: convId })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        typing.remove();
        if (res.ok) {
          convId = res.data.conversation_id;
          try { sessionStorage.setItem(storeKey, convId); } catch (e) {}
          add('bot', res.data.reply);
        } else {
          add('error', res.data.error || 'Something went wrong. Please call us at ' + phone + '.');
        }
      })
      .catch(function () {
        typing.remove();
        add('error', "Can't reach the assistant right now. Please call us at " + phone + '.');
      })
      .finally(function () { send.disabled = false; input.focus(); });
  });
})();
