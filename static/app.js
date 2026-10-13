(() => {
  const viewer = document.getElementById('media-viewer');
  if (!viewer) return;

  const mediaSlot = document.getElementById('viewer-media');
  const caption = document.getElementById('viewer-caption');
  const byline = document.getElementById('viewer-byline');
  const closeButton = viewer.querySelector('.viewer-close');
  let lastFocused = null;
  let cleanupTimer = null;

  const closeViewer = () => {
    if (!viewer.classList.contains('is-open')) return;
    viewer.classList.remove('is-open');
    viewer.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('viewer-active');
    window.clearTimeout(cleanupTimer);
    cleanupTimer = window.setTimeout(() => {
      mediaSlot.replaceChildren();
      if (lastFocused) lastFocused.focus();
    }, 260);
  };

  document.addEventListener('click', event => {
    const trigger = event.target.closest('.media-open');
    if (trigger) {
      window.clearTimeout(cleanupTimer);
      lastFocused = trigger;
      const isVideo = trigger.dataset.kind === 'video';
      const media = document.createElement(isVideo ? 'video' : 'img');
      media.className = 'viewer-asset';
      media.src = trigger.dataset.src;
      if (isVideo) {
        media.controls = true;
        media.autoplay = true;
        media.playsInline = true;
        media.addEventListener('error', () => { media.controls = true; }, { once: true });
      } else {
        media.alt = trigger.dataset.caption || 'Shared photo';
      }
      mediaSlot.replaceChildren(media);
      caption.textContent = trigger.dataset.caption || '';
      byline.textContent = trigger.dataset.byline || '';
      viewer.classList.add('is-open');
      viewer.setAttribute('aria-hidden', 'false');
      document.body.classList.add('viewer-active');
      closeButton.focus();
      return;
    }
    if (event.target.closest('[data-viewer-close]')) closeViewer();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeViewer();
    if (event.key === 'Tab' && viewer.classList.contains('is-open')) {
      const focusables = [...viewer.querySelectorAll('button:not([disabled]), video[controls]')];
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
})();
