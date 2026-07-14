import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import styles from './publicSite.module.css';

export default function PublicNav() {
  return (
    <header className={styles.nav}>
      <Link className={styles.brand} href="/">Arceus</Link>
      <nav className={styles.links} aria-label="Arceus public navigation">
        <Link href="/products">Products</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/docs">Docs</Link>
        <Link href="/download">Download</Link>
        <Link href="/login">Login</Link>
        <Link className={styles.primary} href="/signup">
          Sign up <ArrowRight size={14} />
        </Link>
      </nav>
    </header>
  );
}
