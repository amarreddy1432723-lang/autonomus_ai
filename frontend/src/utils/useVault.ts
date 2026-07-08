'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

const VAULT_SESSION_KEY = 'my-ai.vault_key';
const VAULT_SALT_KEY = 'my-ai.vault_salt';
const ITERATIONS = 600_000;

function bytesToHex(bytes: Uint8Array) {
  return Array.from(bytes).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function hexToBytes(hex: string) {
  const clean = hex.trim();
  const out = new Uint8Array(clean.length / 2);
  for (let index = 0; index < out.length; index += 1) {
    out[index] = Number.parseInt(clean.slice(index * 2, index * 2 + 2), 16);
  }
  return out;
}

function toArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

async function deriveVaultKey(passphrase: string, salt: Uint8Array) {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    toArrayBuffer(new TextEncoder().encode(passphrase)),
    'PBKDF2',
    false,
    ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: toArrayBuffer(salt), iterations: ITERATIONS, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt']
  );
}

async function exportKeyBytes(key: CryptoKey) {
  return new Uint8Array(await crypto.subtle.exportKey('raw', key));
}

export function useVault() {
  const [vaultKey, setVaultKey] = useState<string | null>(null);
  const [saltHex, setSaltHex] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setVaultKey(sessionStorage.getItem(VAULT_SESSION_KEY));
    setSaltHex(localStorage.getItem(VAULT_SALT_KEY));
  }, []);

  const isUnlocked = Boolean(vaultKey);

  const setupVault = useCallback(async (passphrase: string) => {
    const salt = crypto.getRandomValues(new Uint8Array(32));
    const key = await deriveVaultKey(passphrase, salt);
    const keyHex = bytesToHex(await exportKeyBytes(key));
    const nextSaltHex = bytesToHex(salt);
    sessionStorage.setItem(VAULT_SESSION_KEY, keyHex);
    localStorage.setItem(VAULT_SALT_KEY, nextSaltHex);
    setVaultKey(keyHex);
    setSaltHex(nextSaltHex);
    return { salt: nextSaltHex };
  }, []);

  const unlockVault = useCallback(async (passphrase: string, saltOverride?: string) => {
    const selectedSalt = saltOverride || saltHex || localStorage.getItem(VAULT_SALT_KEY);
    if (!selectedSalt) {
      throw new Error('Vault salt is missing. Set up the vault first.');
    }
    const key = await deriveVaultKey(passphrase, hexToBytes(selectedSalt));
    const keyHex = bytesToHex(await exportKeyBytes(key));
    sessionStorage.setItem(VAULT_SESSION_KEY, keyHex);
    setVaultKey(keyHex);
    setSaltHex(selectedSalt);
    return { salt: selectedSalt };
  }, [saltHex]);

  const lockVault = useCallback(() => {
    sessionStorage.removeItem(VAULT_SESSION_KEY);
    setVaultKey(null);
  }, []);

  const encryptText = useCallback(async (plaintext: string) => {
    if (!vaultKey) throw new Error('Vault is locked.');
    const key = await crypto.subtle.importKey('raw', toArrayBuffer(hexToBytes(vaultKey)), 'AES-GCM', false, ['encrypt']);
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = new Uint8Array(await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: toArrayBuffer(nonce) },
      key,
      toArrayBuffer(new TextEncoder().encode(plaintext))
    ));
    return { nonce: bytesToHex(nonce), ciphertext: bytesToHex(ciphertext) };
  }, [vaultKey]);

  const decryptText = useCallback(async (encrypted: { nonce: string; ciphertext: string }) => {
    if (!vaultKey) throw new Error('Vault is locked.');
    const key = await crypto.subtle.importKey('raw', toArrayBuffer(hexToBytes(vaultKey)), 'AES-GCM', false, ['decrypt']);
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: toArrayBuffer(hexToBytes(encrypted.nonce)) },
      key,
      toArrayBuffer(hexToBytes(encrypted.ciphertext))
    );
    return new TextDecoder().decode(plaintext);
  }, [vaultKey]);

  const vaultHeaders = useMemo(() => {
    return vaultKey ? { 'X-Vault-Key': vaultKey } : {};
  }, [vaultKey]);

  return {
    isUnlocked,
    saltHex,
    setupVault,
    unlockVault,
    lockVault,
    encryptText,
    decryptText,
    vaultHeaders,
  };
}
