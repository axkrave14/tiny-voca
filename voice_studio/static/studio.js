'use strict';
const $ = id => document.getElementById(id);
const script = $('script'), generate = $('generate'), status = $('service-status');
let ready = false, busy = false, currentURL = null, currentBlob = null;
function message(text, kind = '') { $('message').textContent = text; $('message').className = 'message ' + kind; }
function update() {
  $('count').textContent = script.value.length.toLocaleString() + ' / 6,000';
  generate.disabled = busy || !ready || !script.value.trim();
}
script.addEventListener('input', update);
$('speed').addEventListener('input', () => { $('speed-value').value = Number($('speed').value).toFixed(2) + '×'; });
async function importScript(file) {
  if (!file) return;
  if (!/\.txt$/i.test(file.name)) return message('Choose a plain-text .txt file.', 'error');
  if (file.size > 40000) return message('This file is too large. Use a script of at most 6,000 characters.', 'error');
  try {
    const text = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer()).replace(/^\uFEFF/, '');
    if (text.length > 6000) return message('This script exceeds 6,000 characters. Split it into smaller parts.', 'error');
    script.value = text; update(); script.focus(); message('Script imported. Choose your voice and generate.');
  } catch { message('Could not read this file. Save it as UTF-8 plain text and try again.', 'error'); }
}
$('script-file').addEventListener('change', event => { importScript(event.target.files[0]); event.target.value = ''; });
script.addEventListener('dragover', event => { event.preventDefault(); script.classList.add('drag'); });
script.addEventListener('dragleave', () => script.classList.remove('drag'));
script.addEventListener('drop', event => { event.preventDefault(); script.classList.remove('drag'); importScript(event.dataTransfer.files[0]); });
script.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); if (!generate.disabled) $('speech-form').requestSubmit(); }
});
$('speech-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (generate.disabled) return;
  const voice = document.querySelector('input[name="voice"]:checked').value;
  busy = true; document.body.classList.add('busy'); $('generate-label').textContent = 'Generating…'; update();
  message('Generating your voiceover. Longer scripts may take a few minutes.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 270000);
  try {
    const headers = {'Content-Type': 'application/json'};
    if ($('access-key').value) headers.Authorization = 'Bearer ' + $('access-key').value;
    const response = await fetch('/api/speech', {method:'POST', headers, signal:controller.signal,
      body:JSON.stringify({text:script.value, voice, speed:Number($('speed').value)})});
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Could not generate speech. Please try again.');
    }
    if (!response.headers.get('content-type')?.includes('audio/wav')) throw new Error('The server did not return an audio file.');
    const blob = await response.blob();
    if (blob.size < 44) throw new Error('The audio file was empty. Try a different script.');
    const oldURL = currentURL;
    currentBlob = blob; currentURL = URL.createObjectURL(blob);
    $('audio').src = currentURL; $('audio').load(); $('download').href = currentURL;
    if (oldURL) URL.revokeObjectURL(oldURL);
    const duration = Number(response.headers.get('X-Audio-Duration'));
    const timing = Number.isFinite(duration) && duration > 0 ? Math.round(duration) + ' sec · ' : '';
    $('audio-details').textContent = timing + (voice === 'M2' ? 'Male' : 'Female') + ' · WAV';
    $('result').hidden = false;
    $('share').hidden = !(navigator.canShare && navigator.canShare({files:[new File([blob], 'tiny-voca-narration.wav', {type:'audio/wav'})]}));
    message('Your voiceover is ready. Press play or download the WAV.', 'success');
    $('result').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'nearest'});
  } catch(error) {
    message(error.name === 'AbortError' ? 'The request timed out. Try a shorter script.' : error.message, 'error');
  } finally {
    clearTimeout(timer); busy = false; document.body.classList.remove('busy'); $('generate-label').textContent = 'Generate voiceover'; update();
  }
});
$('share').addEventListener('click', async () => {
  if (!currentBlob) return;
  try { await navigator.share({files:[new File([currentBlob], 'tiny-voca-narration.wav', {type:'audio/wav'})], title:'My voiceover'}); }
  catch(error) { if (error.name !== 'AbortError') message('Sharing was unavailable. Use Download WAV instead.', 'error'); }
});
async function connect() {
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('Could not reach the voice engine.');
    const config = await response.json(); ready = config.ready;
    $('key-section').hidden = !config.requires_key;
    status.className = 'status ' + (ready ? 'ready' : 'error');
    status.replaceChildren(Object.assign(document.createElement('i')), document.createTextNode(ready ? 'Voice engine ready' : 'Model setup needed'));
    if (!ready) message('The app is running. Install the model files on the server to enable speech.', 'error');
  } catch {
    ready = false; status.className = 'status error'; status.textContent = 'Engine unavailable';
    message('Could not connect to the voice engine. Reload this page to try again.', 'error');
  }
  update();
}
connect();
