// Only these three OS actions are accepted. Never accept an arbitrary URL.
function contactUrl({ kind, address, subject = '', body = '' } = {}) {
  if (typeof address !== 'string' || /[\r\n\x00-\x1f]/.test(address)) throw new Error('Invalid contact address.');
  address = address.trim();
  if (typeof subject !== 'string' || typeof body !== 'string' || subject.length > 200 || body.length > 2000 || /[\r\n]/.test(subject)) throw new Error('Invalid message.');
  if (kind === 'email') {
    if (address.length > 254 || !/^[^\s@<>?&#]+@[^\s@<>?&#]+\.[^\s@<>?&#]+$/.test(address)) throw new Error('Invalid email address.');
    return `mailto:${encodeURIComponent(address)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
  if (!['sms', 'call'].includes(kind) || !/^\+?[0-9 ()\-.]{3,40}$/.test(address)) throw new Error('Invalid phone number.');
  const phone = address.replace(/[ ()\-.]/g, '');
  if (!/^\+?\d{3,20}$/.test(phone)) throw new Error('Invalid phone number.');
  return kind === 'sms' ? `sms:${phone}?body=${encodeURIComponent(body)}` : `tel:${phone}`;
}

module.exports = { contactUrl };
