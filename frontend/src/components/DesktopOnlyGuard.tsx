'use client';

import Link from 'next/link';
import { ArrowLeft, Monitor } from 'lucide-react';
import styles from './DesktopOnlyGuard.module.css';

type DesktopOnlyGuardProps = {
  product: string;
  reason: string;
  children: React.ReactNode;
};

export default function DesktopOnlyGuard({ product, reason, children }: DesktopOnlyGuardProps) {
  return (
    <>
      <div className={styles.desktopContent}>{children}</div>
      <main className={styles.mobileBlock}>
        <section className={styles.message}>
          <div className={styles.icon}>
            <Monitor size={22} />
          </div>
          <p className={styles.eyebrow}>Desktop required</p>
          <h1>{product}</h1>
          <p>{reason}</p>
          <div className={styles.actions}>
            <Link className={styles.primary} href="/hub">
              <ArrowLeft size={15} />
              Product Hub
            </Link>
            <Link className={styles.secondary} href="/pa">
              Open Arceus PA
            </Link>
          </div>
        </section>
      </main>
    </>
  );
}
