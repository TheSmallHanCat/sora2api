import React from "react";
import type { Account } from "../api/types";
import styles from "../App.module.css";

interface Props {
  account: Account | null;
}

export const AccountInfo: React.FC<Props> = ({ account }) => {
  if (!account) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>Account Info</h3>
      <div className={styles.statsGrid}>
        <div className={styles.statItem}>
          <span className={styles.statLabel}>Plan</span>
          <span className={styles.statValue}>
            {account.plan_title || "N/A"}
          </span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statLabel}>Status</span>
          <span
            className={styles.statValue}
            style={{
              color: account.is_active ? "var(--success)" : "var(--error)"
            }}
          >
            {account.is_active ? "Active" : "Inactive"}
          </span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statLabel}>Sora2 Remaining</span>
          <span className={styles.statValue}>
            {account.sora2_remaining_count} / {account.sora2_total_count}
          </span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statLabel}>Generated</span>
          <span className={styles.statValue}>{account.video_count} Videos</span>
        </div>
      </div>
    </div>
  );
};
