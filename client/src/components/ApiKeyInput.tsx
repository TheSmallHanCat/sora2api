import React, { useState, useEffect } from "react";
import styles from "../App.module.css";

export const ApiKeyInput: React.FC = () => {
  const [apiKey, setApiKey] = useState(
    () => localStorage.getItem("api_key") || "han1234"
  );

  useEffect(() => {
    localStorage.setItem("api_key", apiKey);
  }, [apiKey]);

  return (
    <div className={styles.inputGroup}>
      <label className={styles.label}>API Key</label>
      <input
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder="Enter API Key"
      />
    </div>
  );
};
