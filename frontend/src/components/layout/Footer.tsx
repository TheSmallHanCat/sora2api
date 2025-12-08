import React from 'react';
import styles from './Footer.module.css';

export const Footer: React.FC = () => {
  return (
    <footer className={styles.footer}>
      <p className={styles.text}>
        © 2025{' '}
        <a
          href="https://linux.do/u/thesmallhancat/summary"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.link}
        >
          TheSmallHanCat
        </a>{' '}
        &&{' '}
        <a
          href="https://linux.do/u/tibbar/summary"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.link}
        >
          Tibbar
        </a>
        . All rights reserved.
      </p>
    </footer>
  );
};
