// Keep optional contacts empty; do not guess a country code for local numbers.
export function normalizePhone(value: string): string {
  const phone = value.trim().replace(/[\s().-]/g, '');
  if (phone && !/^\+?[0-9]{7,15}$/.test(phone)) {
    throw new Error('Enter 7–15 digits, optionally starting with + and a country code (for example +919876543210).');
  }
  return phone;
}

export function normalizeEmail(value: string): string {
  const email = value.trim();
  if (email && (email.length > 254 || !/^[^\s@?&#%]+@[^\s@?&#%]+\.[^\s@?&#%]+$/.test(email))) {
    throw new Error('Enter a valid email address, for example test@example.com.');
  }
  return email;
}
