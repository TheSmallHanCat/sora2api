import React from "react";
import type { Account } from "../api/types";
import styles from "../App.module.css";

interface Props {
  accounts: Account[];
  selectedEmail: string;
  onSelect: (email: string) => void;
}

export const AccountSelector: React.FC<Props> = ({
  accounts,
  selectedEmail,
  onSelect
}) => {
  return (
    <div className={styles.inputGroup}>
      <label className={styles.label}>Account</label>
      <select value={selectedEmail} onChange={(e) => onSelect(e.target.value)}>
        <option value="">Select an account</option>
        {accounts.map((account) => (
          <option key={account.email} value={account.email}>
            {account.email} ({account.plan_title || "Free"})
          </option>
        ))}
      </select>
    </div>
  );
};
