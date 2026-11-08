/* Chat AI nổi: bấm nút -> mở khung chat ngay trên trang, KHÔNG chuyển trang.
   Hỏi qua GET /ai/assistant/stream?q=... (SSE: meta -> delta... -> done).
   Dùng fetch + ReadableStream (thay EventSource) để đọc được cả lỗi 429/503.
   Cuộc trò chuyện lưu trong sessionStorage nên vẫn còn khi chuyển sang trang khác của shop. */
(function () {
  'use strict';
  const launcher = document.getElementById('ai-chat-launcher');
  const panel = document.getElementById('ai-chat-panel');
  if (!launcher || !panel) return;

  const log = document.getElementById('ai-chat-log');
  const form = document.getElementById('ai-chat-form');
  const input = document.getElementById('ai-chat-input');
  const sendBtn = document.getElementById('ai-chat-send');
  const STREAM_URL = panel.dataset.streamUrl;
  const KEY = 'aiChatV1';
  const SUGGESTIONS = ['Có tai nghe nào dưới 500k không?', 'Thanh toán thế nào?', 'Đặt hàng như thế nào?'];

  let state = { open: false, messages: [] };   // messages: {role:'user'|'bot', text, error?}
  let controller = null;                        // AbortController của câu đang stream
  let busy = false;

  /* ---------- lưu / khôi phục ---------- */
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* bỏ qua */ }
  }
  function restore() {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) {
        const s = JSON.parse(raw);
        if (s && Array.isArray(s.messages)) state = { open: !!s.open, messages: s.messages.slice(-30) };
      }
    } catch (e) { /* bỏ qua */ }
  }

  /* ---------- hiển thị ---------- */
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function fillText(node, text, role) {
    const displayText = role === 'bot' ? text.replace(/\s*\[\d+\]/g, '') : text;
    node.textContent = displayText;
  }
  function renderMessage(m) {
    const wrap = el('div', 'ai-msg ai-msg--' + m.role + (m.error ? ' ai-msg--error' : ''));
    const body = el('div', 'ai-msg__body');
    fillText(body, m.text || '', m.role);
    wrap.appendChild(body);
    return wrap;
  }
  function renderWelcome() {
    const w = el('div', 'ai-msg ai-msg--bot');
    w.appendChild(el('div', 'ai-msg__body', 'Xin chào! Mình có thể giúp bạn tìm sản phẩm, hướng dẫn đặt hàng và thanh toán. Bạn thử hỏi:'));
    const chips = el('div', 'ai-chips');
    SUGGESTIONS.forEach(s => {
      const b = el('button', 'ai-chip', s); b.type = 'button';
      b.addEventListener('click', () => ask(s));
      chips.appendChild(b);
    });
    w.appendChild(chips);
    return w;
  }
  function renderAll() {
    log.textContent = '';
    if (!state.messages.length) log.appendChild(renderWelcome());
    state.messages.forEach(m => log.appendChild(renderMessage(m)));
    scrollDown();
  }
  function scrollDown() { log.scrollTop = log.scrollHeight; }

  /* ---------- mở / đóng ---------- */
  function setOpen(open, focus) {
    state.open = open;
    panel.hidden = !open;
    launcher.setAttribute('aria-expanded', String(open));
    launcher.classList.toggle('is-open', open);
    if (open) { scrollDown(); if (focus !== false) input.focus(); }
    save();
  }
  launcher.setAttribute('role', 'button');
  launcher.setAttribute('aria-controls', 'ai-chat-panel');
  launcher.addEventListener('click', e => {
    // Ctrl/Cmd/Shift+click hoặc chuột giữa: vẫn mở trang đầy đủ như liên kết thường.
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    setOpen(!state.open);
  });
  document.getElementById('ai-chat-close').addEventListener('click', () => { setOpen(false); launcher.focus(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && state.open) { setOpen(false); launcher.focus(); }
  });
  document.getElementById('ai-chat-clear').addEventListener('click', () => {
    if (controller) controller.abort();
    state.messages = []; busy = false; setBusy(false); save(); renderAll(); input.focus();
  });

  function setBusy(b) {
    busy = b; sendBtn.disabled = b; input.disabled = false;
    sendBtn.textContent = b ? '…' : 'Gửi';
  }

  /* ---------- gọi AI (SSE qua fetch) ---------- */
  function parseBlock(block) {
    let event = 'message'; const data = [];
    block.split('\n').forEach(line => {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    });
    if (!data.length) return null;
    try { return { event, data: JSON.parse(data.join('\n')) }; } catch (e) { return null; }
  }

  async function ask(question) {
    question = (question || '').trim();
    if (!question || busy) return;
    if (!state.open) setOpen(true, false);
    state.messages.push({ role: 'user', text: question });
    const bot = { role: 'bot', text: '' };
    state.messages.push(bot);
    renderAll();
    const botNode = log.lastElementChild;
    const body = botNode.querySelector('.ai-msg__body');
    body.classList.add('is-typing');
    setBusy(true);
    controller = new AbortController();

    const show = () => { fillText(body, bot.text, bot.role); scrollDown(); };
    const fail = msg => { bot.error = true; bot.text = (bot.text ? bot.text + '\n' : '') + msg; };
    try {
      const resp = await fetch(STREAM_URL + '?q=' + encodeURIComponent(question), {
        headers: { Accept: 'text/event-stream' }, signal: controller.signal, credentials: 'same-origin'
      });
      const type = resp.headers.get('content-type') || '';
      if (!type.includes('text/event-stream')) {
        fail(resp.status === 401 || resp.redirected
          ? 'Bạn cần đăng nhập để dùng trợ lý AI.'
          : 'Không nhận được phản hồi từ trợ lý (mã ' + resp.status + ').');
      } else {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n');
          let i;
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const ev = parseBlock(buf.slice(0, i)); buf = buf.slice(i + 2);
            if (!ev) continue;
            if (ev.event === 'llm_error') fail(ev.data.error || 'Lỗi dịch vụ AI.');
            else if (typeof ev.data.delta === 'string') bot.text += ev.data.delta;
            show();
          }
        }
        if (!bot.text) fail('Trợ lý chưa có câu trả lời, bạn thử hỏi lại nhé.');
      }
    } catch (e) {
      if (e.name === 'AbortError') return;   // đã xóa hội thoại giữa chừng
      fail('Mất kết nối tới trợ lý, vui lòng thử lại.');
    } finally {
      if (controller && !controller.signal.aborted) {
        body.classList.remove('is-typing');
        setBusy(false); save(); renderAll();
        if (state.open) input.focus();
      }
    }
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    const q = input.value; input.value = '';
    ask(q);
  });

  restore();
  renderAll();
  setOpen(state.open, false);
})();
