import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import styles from './publicSite.module.css';

export default function PublicNav() {
  return (
    <header className={styles.nav}>
      <Link className={styles.brand} href="/">
        <span className={styles.brandMark}>A</span>
        <span>Arceus</span>
      </Link>
      <nav className={styles.links} aria-label="Arceus public navigation">
        <Link href="/products">Products</Link>
        <Link href="/docs">Docs</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/enterprise">Enterprise</Link>
        <Link href="/download">Download</Link>
        <Link href="/sign-in">Sign In</Link>
        <Link className={styles.primary} href="/download">
          Get Started <ArrowRight size={14} />
        </Link>
      </nav>
    </header>
  );
}
