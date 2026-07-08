function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

export function generateSaltHex(): string {
  if (typeof window === 'undefined') return '';
  const bytes = new Uint8Array(32);
  window.crypto.getRandomValues(bytes);
  return bytesToHex(bytes);
}

export async function deriveVaultKey(passphrase: string, saltHex: string): Promise<string> {
  if (typeof window === 'undefined') return '';
  const encoder = new TextEncoder();
  const passphraseBytes = encoder.encode(passphrase);
  const saltBytes = hexToBytes(saltHex);

  const baseKey = await window.crypto.subtle.importKey(
    'raw',
    passphraseBytes,
    'PBKDF2',
    false,
    ['deriveBits']
  );

  const derivedBits = await window.crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      salt: saltBytes as any,
      iterations: 600000,
      hash: 'SHA-256'
    },
    baseKey,
    256 // 32 bytes * 8 bits
  );

  return bytesToHex(new Uint8Array(derivedBits));
}

export function getVaultKey(): string | null {
  if (typeof window === 'undefined') return null;
  return window.sessionStorage.getItem('my-ai.vault_key');
}

export function setVaultKey(keyHex: string): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem('my-ai.vault_key', keyHex);
}

export function clearVaultKey(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem('my-ai.vault_key');
}
