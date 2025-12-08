import React, { useState, useEffect } from 'react';
import { Modal, Button, Textarea, Input, Checkbox } from '../common';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import type { Token } from '../../types';
import styles from './TokenModal.module.css';

interface EditTokenModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  token: Token | null;
}

export const EditTokenModal: React.FC<EditTokenModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  token,
}) => {
  const [at, setAt] = useState('');
  const [st, setSt] = useState('');
  const [rt, setRt] = useState('');
  const [clientId, setClientId] = useState('');
  const [remark, setRemark] = useState('');
  const [imageEnabled, setImageEnabled] = useState(true);
  const [videoEnabled, setVideoEnabled] = useState(true);
  const [imageConcurrency, setImageConcurrency] = useState('-1');
  const [videoConcurrency, setVideoConcurrency] = useState('-1');
  const [isLoading, setIsLoading] = useState(false);
  const [rtRefreshed, setRtRefreshed] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    if (token && isOpen) {
      setAt(token.token || '');
      setSt(token.st || '');
      setRt(token.rt || '');
      setClientId(token.client_id || '');
      setRemark(token.remark || '');
      setImageEnabled(token.image_enabled !== false);
      setVideoEnabled(token.video_enabled !== false);
      setImageConcurrency(String(token.image_concurrency ?? -1));
      setVideoConcurrency(String(token.video_concurrency ?? -1));
      setRtRefreshed(false);
    }
  }, [token, isOpen]);

  const handleClose = () => {
    setRtRefreshed(false);
    onClose();
  };

  const handleConvertST = async () => {
    if (!st.trim()) {
      showToast('Сначала введите Session Token', 'error');
      return;
    }
    try {
      showToast('Конвертация ST→AT...', 'info');
      const result = await api.convertST2AT(st.trim());
      if (result.success && result.access_token) {
        setAt(result.access_token);
        showToast('Конвертация успешна! AT автоматически заполнен', 'success');
      } else {
        showToast(`Ошибка конвертации: ${result.message || result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка конвертации: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleConvertRT = async () => {
    if (!rt.trim()) {
      showToast('Сначала введите Refresh Token', 'error');
      return;
    }
    setRtRefreshed(false);
    try {
      showToast('Конвертация RT→AT...', 'info');
      const result = await api.convertRT2AT(rt.trim());
      if (result.success && result.access_token) {
        setAt(result.access_token);
        if (result.refresh_token) {
          setRt(result.refresh_token);
          setRtRefreshed(true);
          showToast('Конвертация успешна! AT автоматически заполнен, RT обновлён', 'success');
        } else {
          showToast('Конвертация успешна! AT автоматически заполнен', 'success');
        }
      } else {
        showToast(`Ошибка конвертации: ${result.message || result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка конвертации: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSubmit = async () => {
    if (!token) return;
    if (!at.trim()) {
      showToast('Введите Access Token', 'error');
      return;
    }

    setIsLoading(true);
    try {
      const result = await api.updateToken(token.id, {
        token: at.trim(),
        st: st.trim() || null,
        rt: rt.trim() || null,
        client_id: clientId.trim() || null,
        remark: remark.trim() || null,
        image_enabled: imageEnabled,
        video_enabled: videoEnabled,
        image_concurrency: parseInt(imageConcurrency) || null,
        video_concurrency: parseInt(videoConcurrency) || null,
      });

      if (result.success) {
        handleClose();
        onSuccess();
        showToast('Token успешно обновлён', 'success');
      } else {
        showToast(`Ошибка обновления: ${result.detail || result.message || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка обновления: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Редактировать Token"
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={handleClose}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} loading={isLoading}>
            Сохранить
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>
            Access Token (AT) <span className={styles.required}>*</span>
          </label>
          <Textarea
            value={at}
            onChange={(e) => setAt(e.target.value)}
            rows={3}
            placeholder="Введите Access Token или используйте ST/RT конвертацию ниже"
            className={styles.mono}
          />
          <p className={styles.hint}>Формат: eyJh... (JWT формат)</p>
        </div>

        <div className={styles.field}>
          <label className={styles.label}>
            Session Token (ST) <span className={styles.optional}>- опционально</span>
          </label>
          <div className={styles.inputRow}>
            <Textarea
              value={st}
              onChange={(e) => setSt(e.target.value)}
              rows={2}
              placeholder="Введите Session Token и нажмите конвертировать"
              className={styles.mono}
            />
            <Button variant="blue" onClick={handleConvertST} className={styles.convertBtn}>
              ST→AT
            </Button>
          </div>
          <p className={styles.hint}>Получите из Cookie браузера __Secure-next-auth.session-token</p>
        </div>

        <div className={styles.field}>
          <label className={styles.label}>
            Refresh Token (RT) <span className={styles.optional}>- опционально</span>
          </label>
          <div className={styles.inputRow}>
            <Textarea
              value={rt}
              onChange={(e) => setRt(e.target.value)}
              rows={2}
              placeholder="Введите Refresh Token и нажмите конвертировать"
              className={styles.mono}
            />
            <Button variant="green" onClick={handleConvertRT} className={styles.convertBtn}>
              RT→AT
            </Button>
          </div>
          <p className={styles.hint}>Получите из мобильного приложения или другого клиента</p>
          {rtRefreshed && (
            <p className={styles.successHint}>✓ RT обновлён, заполнен новый RT</p>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label}>
            Client ID <span className={styles.optional}>- опционально</span>
          </label>
          <Input
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="Оставьте пустым для значения по умолчанию"
            className={styles.mono}
          />
          <p className={styles.hint}>Используется для обновления RT, оставьте пустым для Client ID по умолчанию</p>
        </div>

        <div className={styles.field}>
          <label className={styles.label}>
            Примечание <span className={styles.optional}>- опционально</span>
          </label>
          <Input
            value={remark}
            onChange={(e) => setRemark(e.target.value)}
            placeholder="Добавьте примечание"
          />
        </div>

        <div className={styles.separator}>
          <label className={styles.label}>Переключатели функций</label>
          <div className={styles.toggleRow}>
            <Checkbox
              checked={imageEnabled}
              onChange={setImageEnabled}
              label="Включить генерацию изображений"
            />
            <input
              type="number"
              value={imageConcurrency}
              onChange={(e) => setImageConcurrency(e.target.value)}
              className={styles.concurrencyInput}
              placeholder="Параллельно"
              title="Лимит параллельных запросов: максимальное количество одновременных запросов. -1 = без ограничений"
            />
          </div>
          <div className={styles.toggleRow}>
            <Checkbox
              checked={videoEnabled}
              onChange={setVideoEnabled}
              label="Включить генерацию видео"
            />
            <input
              type="number"
              value={videoConcurrency}
              onChange={(e) => setVideoConcurrency(e.target.value)}
              className={styles.concurrencyInput}
              placeholder="Параллельно"
              title="Лимит параллельных запросов: максимальное количество одновременных запросов. -1 = без ограничений"
            />
          </div>
        </div>
      </div>
    </Modal>
  );
};
