const file = document.querySelector('#file');
const preview = document.querySelector('#preview');
const empty = document.querySelector('#empty');
const button = document.querySelector('#classify');
let imageData = null;

file.addEventListener('change', () => {
  const selected = file.files[0];
  if (!selected) return;
  const reader = new FileReader();
  reader.onload = e => {
    imageData = e.target.result;
    preview.src = imageData;
    preview.style.display = 'block';
    empty.style.display = 'none';
    button.disabled = false;
  };
  reader.readAsDataURL(selected);
});

document.querySelector('#another').addEventListener('click', () => {
  imageData = null;
  file.value = '';
  preview.removeAttribute('src');
  preview.style.display = 'none';
  empty.style.display = 'block';
  button.disabled = true;
  document.querySelector('.result h2').textContent = 'Awaiting scan';
  document.querySelector('.result-empty').hidden = false;
  document.querySelector('.decision').hidden = true;
  document.querySelector('.pill').textContent = 'READY';
  file.click();
});

button.addEventListener('click', async () => {
  if (!imageData) return;
  button.disabled = true;
  button.textContent = 'Analysing…';
  try {
    const response = await fetch('/api/classify', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image: imageData, hint: 'auto'})});
    if (!response.ok) throw Error(await response.text());
    showResult(await response.json());
    await refresh();
  } catch (error) {
    alert('We could not classify that image. Please try another photo.');
  } finally {
    button.disabled = false;
    button.innerHTML = 'Classify item <span>→</span>';
  }
});

function showResult(data) {
  document.querySelector('.result h2').textContent = data.label;
  document.querySelector('.result-empty').hidden = true;
  document.querySelector('.decision').hidden = false;
  document.querySelector('#route').textContent = data.route;
  document.querySelector('#recyclable').textContent = data.recyclable ? 'Recyclable / recoverable' : 'Not for regular recycling';
  document.querySelector('#tip').textContent = data.suggestions;
  const icon = document.querySelector('#bin-icon');
  icon.textContent = data.bin_color === 'blue' ? '♻' : data.bin_color === 'green' ? '♲' : '⚠';
  icon.dataset.color = data.bin_color;
  document.querySelector('#confidence').textContent = Math.round(data.confidence * 100) + '%';
  document.querySelector('#bar').style.width = (data.confidence * 100) + '%';
  document.querySelector('#review').textContent = data.review_required ? 'Low confidence — check the item before sorting.' : 'Check local collection rules; bin colors vary by location.';
  document.querySelector('.pill').textContent = data.review_required ? 'REVIEW' : 'SORTED';
}

const labels = {plastic: 'Plastic', paper: 'Paper', metal: 'Metal', glass: 'Glass', organic: 'Organic', hazardous: 'Hazardous', general: 'General'};
async function refresh() {
  const [stats, events] = await Promise.all([fetch('/api/stats').then(r => r.json()), fetch('/api/events').then(r => r.json())]);
  document.querySelector('#total').textContent = stats.total;
  document.querySelector('#reviews').textContent = stats.review_required;
  document.querySelector('#recycle').textContent = ['plastic', 'paper', 'metal', 'glass', 'organic'].reduce((sum, key) => sum + stats.distribution[key], 0);
  const max = Math.max(1, ...Object.values(stats.distribution));
  document.querySelector('#bars').innerHTML = Object.entries(stats.distribution).map(([key, value]) => `<div class="bar"><span style="height:${Math.max(value ? 12 : 2, value / max * 100)}%"></span><small>${labels[key]}</small><b>${value}</b></div>`).join('');
  document.querySelector('#events').innerHTML = events.length ? events.map(event => `<div class="event"><span class="dot"></span><b>${labels[event.category]}</b><span>${Math.round(event.confidence * 100)}% confidence</span><time datetime="${event.created_at}">${new Date(event.created_at).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}</time></div>`).join('') : '<p>There are no scans yet.</p>';
}
refresh();
