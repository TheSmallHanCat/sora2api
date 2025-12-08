import React from 'react';
import type { Stats } from '../../types';
import styles from './StatsCards.module.css';

interface StatsCardsProps {
  stats: Stats | null;
}

export const StatsCards: React.FC<StatsCardsProps> = ({ stats }) => {
  return (
    <div className={styles.grid}>
      <div className={styles.card}>
        <p className={styles.label}>Всего Token</p>
        <h3 className={styles.value}>{stats?.total_tokens ?? '-'}</h3>
      </div>
      <div className={styles.card}>
        <p className={styles.label}>Активных Token</p>
        <h3 className={`${styles.value} ${styles.green}`}>
          {stats?.active_tokens ?? '-'}
        </h3>
      </div>
      <div className={styles.card}>
        <p className={styles.label}>Изображения сегодня/всего</p>
        <h3 className={`${styles.value} ${styles.blue}`}>
          {stats ? `${stats.today_images}/${stats.total_images}` : '-'}
        </h3>
      </div>
      <div className={styles.card}>
        <p className={styles.label}>Видео сегодня/всего</p>
        <h3 className={`${styles.value} ${styles.purple}`}>
          {stats ? `${stats.today_videos}/${stats.total_videos}` : '-'}
        </h3>
      </div>
      <div className={styles.card}>
        <p className={styles.label}>Ошибки сегодня/всего</p>
        <h3 className={`${styles.value} ${styles.red}`}>
          {stats ? `${stats.today_errors}/${stats.total_errors}` : '-'}
        </h3>
      </div>
    </div>
  );
};
