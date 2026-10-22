/* Chat bubble for {{ biz.name }}. Add to any site: <script src="..." async></script> */
(function () {
  var flag = '__chatWidget_{{ biz.slug | replace("-", "_") }}';
  if (window[flag]) return;
  window[flag] = true;

  var chatUrl = {{ chat_url | tojson }};
  var color = {{ biz.brand.primary | tojson }};
  var labels = {{ labels | tojson }};          // "Chat with ..." in each language the business supports
  var mobile = window.matchMedia('(max-width: 480px)');

  // The bubble label follows the visitor's browser language (the chat inside remembers their own choice).
  var label = labels[{{ default_lang | tojson }}];
  var prefs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
  for (var i = 0; i < prefs.length; i++) {
    var code = String(prefs[i] || '').toLowerCase().split('-')[0];
    if (labels[code]) { label = labels[code]; break; }
  }

  var button = document.createElement('button');
  button.setAttribute('aria-label', label);
  button.title = label;
  button.textContent = '💬';
  button.style.cssText = 'position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;' +
    'background:' + color + ';color:#fff;font-size:28px;cursor:pointer;z-index:2147483646;' +
    'box-shadow:0 4px 14px rgba(0,0,0,.3);';

  var frame = document.createElement('iframe');
  frame.title = label;
  frame.style.cssText = 'position:fixed;border:0;z-index:2147483647;display:none;background:#fff;' +
    'box-shadow:0 8px 30px rgba(0,0,0,.3);';

  function place() {
    var s = frame.style;
    if (mobile.matches) {
      s.right = '0'; s.bottom = '0'; s.width = '100%'; s.height = '100%'; s.maxHeight = 'none'; s.borderRadius = '0';
    } else {
      s.right = '20px'; s.bottom = '92px'; s.width = '380px'; s.height = '600px';
      s.maxHeight = 'calc(100vh - 112px)'; s.borderRadius = '14px';
    }
  }

  var loaded = false;
  function setOpen(open) {
    if (open && !loaded) { frame.src = chatUrl; loaded = true; }  // load the chat only when first opened
    place();
    frame.style.display = open ? 'block' : 'none';
    button.textContent = open ? '✕' : '💬';
    // On phones the chat is full screen and has its own close button.
    button.style.display = open && mobile.matches ? 'none' : 'block';
  }

  button.addEventListener('click', function () { setOpen(frame.style.display === 'none'); });
  window.addEventListener('message', function (e) {
    if (e.source === frame.contentWindow && e.data && e.data.type === 'chat-widget-close') setOpen(false);
  });

  document.body.appendChild(frame);
  document.body.appendChild(button);
})();
