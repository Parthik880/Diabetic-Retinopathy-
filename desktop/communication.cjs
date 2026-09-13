// Only these structured actions are exposed; the renderer cannot supply a URL.
function communicationUrl(request) {
  if (!request || typeof request.recipient !== 'string') throw new Error('A recipient is required.');
  const recipient = request.recipient.trim();
  if (request.action === 'email') {
    if (recipient.length > 254 || !/^[^\s@?&#%]+@[^\s@?&#%]+\.[^\s@?&#%]+$/.test(recipient)) throw new Error('Invalid email address.');
    if (typeof request.subject !== 'string' || request.subject.length > 300 || /[\r\n]/.test(request.subject)) throw new Error('Invalid subject.');
    if (typeof request.body !== 'string' || request.body.length > 4000) throw new Error('Invalid message.');
    return `mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(request.subject)}&body=${encodeURIComponent(request.body)}`;
  }
  if (request.action === 'call' && /^\+?[0-9]{7,15}$/.test(recipient)) return `tel:${recipient}`;
  throw new Error('Unsupported communication action or invalid phone number.');
}

async function openCommunication(request, shell) {
  try {
    const url = communicationUrl(request);
    if (!['mailto:', 'tel:'].includes(new URL(url).protocol)) throw new Error('Unsupported scheme.');
    await shell.openExternal(url);
    return { opened: true };
  } catch {
    return { opened: false, error: 'Windows could not open a suitable app. Use the contact details below.' };
  }
}

module.exports = { communicationUrl, openCommunication };
