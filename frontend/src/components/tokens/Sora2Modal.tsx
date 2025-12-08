import React, { useState, useEffect } from 'react';
import { Modal, Button, Input } from '../common';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import styles from './TokenModal.module.css';

interface Sora2ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  tokenId: number | null;
}

export const Sora2Modal: React.FC<Sora2ModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  tokenId,
}) => {
  const [inviteCode, setInviteCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    if (!isOpen) {
      setInviteCode('');
    }
  }, [isOpen]);

  const handleSubmit = async () => {
    if (!tokenId) {
      showToast('Token ID недействителен', 'error');
      return;
    }

    if (!inviteCode.trim()) {
      showToast('Пожалуйста, введите код приглашения', 'error');
      return;
    }

    if (inviteCode.trim().length !== 6) {
      showToast('Код приглашения должен состоять из 6 символов', 'error');
      return;
    }

    setIsLoading(true);
    try {
      showToast('Активация Sora2...', 'info');
      const result = await api.activateSora2(tokenId, inviteCode.trim());

      if (result.success) {
        onClose();
        onSuccess();
        if (result.already_accepted) {
          showToast('Sora2 уже активирован (ранее принят)', 'success');
        } else {
          showToast(`Sora2 успешно активирован! Код приглашения: ${result.invite_code || 'Нет'}`, 'success');
        }
      } else {
        showToast(`Ошибка активации: ${result.message || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка активации: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Активировать Sora2"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} loading={isLoading}>
            Активировать
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>Sora2 Код приглашения</label>
          <Input
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            placeholder="Введите 6-значный код, например: 0ZSKEG"
            maxLength={6}
          />
          <p className={styles.hint}>Введите код приглашения Sora2 для активации функции для этого Token</p>
        </div>
      </div>
    </Modal>
  );
};
