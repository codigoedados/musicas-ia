// Player (página pública)
const player = document.getElementById('player');
if (player) {
  const audio = document.getElementById('audio'), title = document.getElementById('ptitle');
  document.querySelectorAll('.play').forEach(b => b.addEventListener('click', () => {
    const src = b.dataset.src;
    if (!audio.src.endsWith(src)) {
      audio.src = src; title.textContent = b.dataset.title;
      navigator.sendBeacon('/play/' + b.dataset.id, new FormData());
    }
    player.hidden = false; document.body.classList.add('has-player');
    audio.paused ? audio.play() : audio.pause();
  }));
  document.getElementById('pclose').onclick = () => {
    audio.pause(); player.hidden = true; document.body.classList.remove('has-player');
  };
}
// Admin: prévia da capa e duração do MP3
const thumb = document.getElementById('thumb');
if (thumb) thumb.onchange = () => {
  const f = thumb.files[0], p = document.getElementById('thumbprev');
  if (f) { p.src = URL.createObjectURL(f); p.hidden = false; }
};
const mp3 = document.getElementById('audiofile');
if (mp3) mp3.onchange = () => {
  const f = mp3.files[0]; if (!f) return;
  const a = new Audio(URL.createObjectURL(f));
  a.onloadedmetadata = () => document.getElementById('duration').value = Math.round(a.duration);
};
