import React, { useState, useRef } from 'react';
import { Modal, Button } from '../common';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import styles from './TokenModal.module.css';

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ImportModal: React.FC<ImportModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();

  const handleClose = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onClose();
  };

  const handleSubmit = async () => {
    const fileInput = fileInputRef.current;
    if (!fileInput?.files || fileInput.files.length === 0) {
      showToast('Пожалуйста, выберите файл', 'error');
      return;
    }

    const file = fileInput.files[0];
    if (!file.name.endsWith('.json')) {
      showToast('Пожалуйста, выберите JSON файл', 'error');
      return;
    }

    try {
      const fileContent = await file.text();
      const importData = JSON.parse(fileContent);

      if (!Array.isArray(importData)) {
        showToast('Ошибка формата JSON: должен быть массив', 'error');
        return;
      }

      if (importData.length === 0) {
        showToast('JSON файл пуст', 'error');
        return;
      }

      setIsLoading(true);

      const result = await api.importTokens(importData);

      if (result.success) {
        handleClose();
        onSuccess();
        showToast(`Импорт успешен! Добавлено: ${result.added || 0}, Обновлено: ${result.updated || 0}`, 'success');
      } else {
        showToast(`Ошибка импорта: ${result.detail || result.message || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      if (err instanceof SyntaxError) {
        showToast('Ошибка разбора файла: неверный формат JSON', 'error');
      } else {
        showToast(`Ошибка импорта: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Импортировать Token"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={handleClose}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} loading={isLoading}>
            Импортировать
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>Выберите JSON файл</label>
          <input
            type="file"
            ref={fileInputRef}
            accept=".json"
            style={{
              display: 'flex',
              height: '2.25rem',
              width: '100%',
              borderRadius: '0.375rem',
              border: '1px solid hsl(0 0% 89%)',
              backgroundColor: 'hsl(0 0% 100%)',
              padding: '0.5rem 0.75rem',
              fontSize: '0.875rem',
            }}
          />
          <p className={styles.hint}>Выберите экспортированный JSON файл с Token для импорта</p>
        </div>
        <div className={styles.infoBox}>
          <p className={styles.infoText}>
            <strong>Примечание:</strong> Если Email существует, данные будут обновлены, если нет — будут добавлены
          </p>
        </div>
      </div>
    </Modal>
  );
};
