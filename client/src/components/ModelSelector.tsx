import React from "react";
import type { Model } from "../api/types";
import styles from "../App.module.css";

interface Props {
  models: Model[];
  selectedModel: string;
  onSelect: (modelId: string) => void;
}

export const ModelSelector: React.FC<Props> = ({
  models,
  selectedModel,
  onSelect
}) => {
  return (
    <div className={styles.inputGroup}>
      <label className={styles.label}>Model</label>
      <select value={selectedModel} onChange={(e) => onSelect(e.target.value)}>
        <option value="">Select a model</option>
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.id} - {model.description}
          </option>
        ))}
      </select>
    </div>
  );
};
