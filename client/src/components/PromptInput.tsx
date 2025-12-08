import React from "react";
import styles from "../App.module.css";

interface Props {
  prompt: string;
  onChange: (prompt: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export const PromptInput: React.FC<Props> = ({
  prompt,
  onChange,
  onSubmit,
  loading
}) => {
  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>Prompt</h3>
      <div className={styles.inputGroup}>
        <textarea
          className={styles.textarea}
          value={prompt}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Describe your video..."
          disabled={loading}
        />
        <button
          className={styles.button}
          onClick={onSubmit}
          disabled={loading || !prompt.trim()}
        >
          {loading ? "Generating..." : "Generate Video"}
        </button>
      </div>
    </div>
  );
};
